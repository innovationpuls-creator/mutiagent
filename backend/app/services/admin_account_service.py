from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.core.security import hash_password
from app.models import ConversationSession, User, UserCourseKnowledgeOutline, UserProfile, UserYearLearningPath
from app.schemas import (
    AdminAccountBatchRequest,
    AdminAccountCreateRequest,
    AdminAccountImportFailure,
    AdminAccountImportResponse,
    AdminAccountUpdateRequest,
    UserRead,
)
from app.services.auth_service import find_user, to_user_read

CSV_FIELDS = ["username", "identifier", "password", "role", "is_active"]
VALID_ROLES = {"student", "teacher", "admin"}


def list_accounts(session: Session) -> list[UserRead]:
    users = session.exec(select(User).order_by(User.created_at.desc())).all()
    return [to_user_read(user) for user in users]


def create_account(session: Session, payload: AdminAccountCreateRequest) -> UserRead:
    if find_user(session, payload.identifier):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="账号已存在",
        )

    now = datetime.now(timezone.utc)
    user = User(
        uid=str(uuid4()),
        username=payload.username,
        identifier=payload.identifier,
        role=payload.role,
        provider="password",
        password_hash=hash_password(payload.password),
        is_active=payload.is_active,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return to_user_read(user)


def update_account(session: Session, uid: str, payload: AdminAccountUpdateRequest, current_user: User | None = None) -> UserRead:
    user = session.get(User, uid)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="账号不存在",
        )

    existing = find_user(session, payload.identifier)
    if existing and existing.uid != uid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="账号已存在",
        )

    _ensure_not_self_lockout(user, current_user, payload.role, payload.is_active)

    user.username = payload.username
    user.identifier = payload.identifier
    user.role = payload.role
    user.is_active = payload.is_active
    user.updated_at = datetime.now(timezone.utc)
    if payload.password:
        user.password_hash = hash_password(payload.password)

    session.add(user)
    session.commit()
    session.refresh(user)
    return to_user_read(user)


def delete_account(session: Session, uid: str, current_user: User | None = None) -> None:
    user = session.get(User, uid)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="账号不存在",
        )
    if current_user and user.uid == current_user.uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除当前登录管理员",
        )
    _delete_user_owned_rows(session, uid)
    session.delete(user)
    session.commit()


def batch_accounts(session: Session, payload: AdminAccountBatchRequest, current_user: User) -> list[UserRead]:
    users = session.exec(select(User).where(User.uid.in_(payload.uids))).all()
    found_uids = {user.uid for user in users}
    missing_uids = [uid for uid in payload.uids if uid not in found_uids]
    if missing_uids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"账号不存在: {', '.join(missing_uids)}",
        )

    if payload.action == "delete":
        for user in users:
            if user.uid == current_user.uid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="不能删除当前登录管理员",
                )
        for user in users:
            _delete_user_owned_rows(session, user.uid)
            session.delete(user)
        session.commit()
        return list_accounts(session)

    now = datetime.now(timezone.utc)
    for user in users:
        next_role = payload.role if payload.action == "set_role" and payload.role else user.role
        next_active = user.is_active
        if payload.action == "activate":
            next_active = True
        elif payload.action == "deactivate":
            next_active = False
        _ensure_not_self_lockout(user, current_user, next_role, next_active)
        user.role = next_role
        user.is_active = next_active
        user.updated_at = now
        session.add(user)
    session.commit()
    return list_accounts(session)


def import_accounts(session: Session, csv_text: str, current_user: User) -> AdminAccountImportResponse:
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames != CSV_FIELDS:
        return AdminAccountImportResponse(
            created=0,
            updated=0,
            failed=1,
            failures=[
                AdminAccountImportFailure(
                    row=1,
                    reason="CSV 表头必须为 username,identifier,password,role,is_active",
                )
            ],
        )

    created = 0
    updated = 0
    failures: list[AdminAccountImportFailure] = []
    for row_number, row in enumerate(reader, start=2):
        identifier = (row.get("identifier") or "").strip()
        try:
            username = _required(row, "username")
            password = (row.get("password") or "").strip()
            role = _parse_role(row.get("role"))
            is_active = _parse_bool(row.get("is_active"))
            if not identifier:
                raise ValueError("identifier 不能为空")

            existing = find_user(session, identifier)
            if existing:
                _ensure_not_self_lockout(existing, current_user, role, is_active)
                existing.username = username
                existing.role = role
                existing.is_active = is_active
                existing.updated_at = datetime.now(timezone.utc)
                if password:
                    existing.password_hash = hash_password(password)
                session.add(existing)
                updated += 1
                continue

            if not password:
                raise ValueError("新账号 password 不能为空")
            account = User(
                uid=str(uuid4()),
                username=username,
                identifier=identifier,
                role=role,
                provider="password",
                password_hash=hash_password(password),
                is_active=is_active,
            )
            session.add(account)
            created += 1
        except ValueError as exc:
            failures.append(
                AdminAccountImportFailure(
                    row=row_number,
                    identifier=identifier or None,
                    reason=str(exc),
                )
            )

    session.commit()
    return AdminAccountImportResponse(
        created=created,
        updated=updated,
        failed=len(failures),
        failures=failures,
    )


def export_accounts(session: Session) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
    writer.writeheader()
    users = session.exec(select(User).order_by(User.created_at.desc())).all()
    for user in users:
        writer.writerow(
            {
                "username": user.username,
                "identifier": user.identifier,
                "password": "",
                "role": user.role,
                "is_active": "true" if user.is_active else "false",
            }
        )
    return output.getvalue()


def _delete_user_owned_rows(session: Session, uid: str) -> None:
    for model in (
        ConversationSession,
        UserCourseKnowledgeOutline,
        UserYearLearningPath,
        UserProfile,
    ):
        rows = session.exec(select(model).where(model.user_uid == uid)).all()
        for row in rows:
            session.delete(row)


def _ensure_not_self_lockout(user: User, current_user: User | None, role: str, is_active: bool) -> None:
    if not current_user or user.uid != current_user.uid:
        return
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能移除当前登录管理员权限",
        )
    if not is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能停用当前登录管理员",
        )


def _required(row: dict[str, str], key: str) -> str:
    value = (row.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} 不能为空")
    return value


def _parse_role(value: str | None) -> str:
    role = (value or "").strip()
    if role not in VALID_ROLES:
        raise ValueError("role 必须是 student、teacher 或 admin")
    return role


def _parse_bool(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"true", "1", "yes", "y", "启用"}:
        return True
    if normalized in {"false", "0", "no", "n", "停用"}:
        return False
    raise ValueError("is_active 必须是 true 或 false")
