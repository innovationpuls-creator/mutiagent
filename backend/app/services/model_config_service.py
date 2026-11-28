"""Personal model configuration: persistence, masking and capability guards."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.crypto import SecretCipher, mask_secret
from app.model_config_schemas import (
    ADMIN_ONLY_SCENES,
    TOOL_SCENES,
    VISION_SCENES,
    CustomModelUpsert,
    CustomModelView,
    ModelConfigView,
    ModelRef,
    PreferencesPayload,
    PreferencesView,
    ProviderUpsert,
    ProviderView,
    QuickSwitchPayload,
    RuntimeOptions,
    UsageBucket,
    UsageRecordPayload,
    UsageSummary,
)
from app.models import (
    User,
    UserCustomModel,
    UserModelPreferences,
    UserModelProvider,
    UserModelUsageLog,
)
from app.services.ai_gateway_client import AiGatewayClient, AiGatewayUnavailableError


class ModelConfigError(Exception):
    def __init__(
        self, status_code: int, detail: str, error_code: str | None = None
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.error_code = error_code


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _new_id() -> str:
    return uuid.uuid4().hex


def fingerprint(value: str | None) -> str:
    """Stable, non-reversible token used for compare-and-swap on refresh tokens."""
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------- providers


def _decrypt_headers(row: UserModelProvider, cipher: SecretCipher) -> dict[str, str]:
    if not row.headers_encrypted:
        return {}
    return json.loads(cipher.decrypt(row.headers_encrypted))


def _oauth_status(row: UserModelProvider) -> str | None:
    if row.auth_type != "oauth" or not row.secret_encrypted:
        return None
    if row.oauth_expires_at and row.oauth_expires_at <= _now():
        return "expired"
    return "authorized"


def provider_view(row: UserModelProvider, cipher: SecretCipher) -> ProviderView:
    secret_mask: str | None = None
    if row.auth_type == "api_key" and row.secret_encrypted:
        secret_mask = mask_secret(cipher.decrypt(row.secret_encrypted))
    headers = {name: "••••" for name in _decrypt_headers(row, cipher)}
    return ProviderView(
        provider_id=row.provider_id,
        display_name=row.display_name,
        is_builtin=row.is_builtin,
        protocol=row.protocol,
        base_url=row.base_url,
        headers=headers,
        auth_type=row.auth_type,  # type: ignore[arg-type]
        has_secret=bool(row.secret_encrypted),
        secret_mask=secret_mask,
        oauth_status=_oauth_status(row),  # type: ignore[arg-type]
        oauth_expires_at=row.oauth_expires_at,
        oauth_account_label=row.oauth_account_label,
        enabled=row.enabled,
        updated_at=row.updated_at,
    )


def _get_provider(
    session: Session, user_uid: str, provider_id: str, *, for_update: bool = False
) -> UserModelProvider | None:
    statement = select(UserModelProvider).where(
        UserModelProvider.user_uid == user_uid,
        UserModelProvider.provider_id == provider_id,
    )
    if for_update:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )
    return session.exec(statement).first()


def upsert_provider(
    session: Session,
    user_uid: str,
    provider_id: str,
    payload: ProviderUpsert,
    cipher: SecretCipher,
) -> UserModelProvider:
    if not payload.is_builtin and (not payload.protocol or not payload.base_url):
        raise ModelConfigError(422, "自定义 Provider 必须填写协议族与 Base URL")
    row = _get_provider(session, user_uid, provider_id, for_update=True)
    if row is None:
        row = UserModelProvider(
            id=_new_id(), user_uid=user_uid, provider_id=provider_id
        )
    row.display_name = payload.display_name or row.display_name or provider_id
    row.is_builtin = payload.is_builtin
    row.protocol = payload.protocol or ""
    row.base_url = (payload.base_url or "").strip()
    row.enabled = payload.enabled
    if row.auth_type != payload.auth_type:
        row.secret_encrypted = None
        row.oauth_refresh_encrypted = None
        row.oauth_expires_at = None
        row.oauth_account_label = None
    row.auth_type = payload.auth_type
    if payload.headers is not None:
        row.headers_encrypted = (
            cipher.encrypt(json.dumps(payload.headers, ensure_ascii=False))
            if payload.headers
            else None
        )
    if payload.api_key is not None and payload.auth_type == "api_key":
        row.secret_encrypted = (
            cipher.encrypt(payload.api_key.strip()) if payload.api_key.strip() else None
        )
    row.updated_at = _now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def delete_provider(session: Session, user_uid: str, provider_id: str) -> bool:
    row = _get_provider(session, user_uid, provider_id)
    if row is None:
        return False
    for model in session.exec(
        select(UserCustomModel).where(
            UserCustomModel.user_uid == user_uid,
            UserCustomModel.provider_id == provider_id,
        )
    ).all():
        session.delete(model)
    session.delete(row)
    session.commit()
    return True


# ------------------------------------------------------------ custom models


def custom_model_view(row: UserCustomModel) -> CustomModelView:
    return CustomModelView(
        id=row.id,
        provider_id=row.provider_id,
        model_id=row.model_id,
        display_name=row.display_name,
        context_window=row.context_window,
        max_tokens=row.max_tokens,
        supports_vision=row.supports_vision,
        supports_tools=row.supports_tools,
        supports_reasoning=row.supports_reasoning,
        compat_config=row.compat_config or {},
        pricing=row.pricing or {},
        enabled=row.enabled,
        updated_at=row.updated_at,
    )


def upsert_custom_model(
    session: Session, user_uid: str, payload: CustomModelUpsert
) -> UserCustomModel:
    provider = _get_provider(session, user_uid, payload.provider_id)
    if provider is None:
        raise ModelConfigError(404, "请先创建对应的 Provider")
    if provider.is_builtin:
        raise ModelConfigError(422, "内置 Provider 使用模型目录，不能添加自定义模型")
    row = session.exec(
        select(UserCustomModel).where(
            UserCustomModel.user_uid == user_uid,
            UserCustomModel.provider_id == payload.provider_id,
            UserCustomModel.model_id == payload.model_id,
        )
    ).first()
    if row is None:
        row = UserCustomModel(
            id=_new_id(),
            user_uid=user_uid,
            provider_id=payload.provider_id,
            model_id=payload.model_id,
        )
    row.display_name = payload.display_name or payload.model_id
    row.context_window = payload.context_window
    row.max_tokens = payload.max_tokens
    row.supports_vision = payload.supports_vision
    row.supports_tools = payload.supports_tools
    row.supports_reasoning = payload.supports_reasoning
    row.compat_config = payload.compat_config
    row.pricing = payload.pricing
    row.enabled = payload.enabled
    row.updated_at = _now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def delete_custom_model(session: Session, user_uid: str, model_row_id: str) -> bool:
    row = session.exec(
        select(UserCustomModel).where(
            UserCustomModel.user_uid == user_uid, UserCustomModel.id == model_row_id
        )
    ).first()
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True


# -------------------------------------------------------------- preferences


def _preferences_view(row: UserModelPreferences | None) -> PreferencesView:
    if row is None:
        return PreferencesView()
    return PreferencesView(
        config_mode=row.config_mode,  # type: ignore[arg-type]
        default_model_ref=row.default_model_ref,
        default_vision_model_ref=row.default_vision_model_ref,
        default_thinking_level=row.default_thinking_level,  # type: ignore[arg-type]
        runtime_options=RuntimeOptions(**(row.runtime_options or {})),
        slot_bindings=row.slot_bindings or {},  # type: ignore[arg-type]
        updated_at=row.updated_at,
    )


def get_config_view(
    session: Session, user_uid: str, cipher: SecretCipher
) -> ModelConfigView:
    providers = session.exec(
        select(UserModelProvider)
        .where(UserModelProvider.user_uid == user_uid)
        .order_by(UserModelProvider.provider_id)
    ).all()
    models = session.exec(
        select(UserCustomModel)
        .where(UserCustomModel.user_uid == user_uid)
        .order_by(UserCustomModel.provider_id, UserCustomModel.model_id)
    ).all()
    return ModelConfigView(
        providers=[provider_view(row, cipher) for row in providers],
        custom_models=[custom_model_view(row) for row in models],
        preferences=_preferences_view(session.get(UserModelPreferences, user_uid)),
    )


def _capability_key(ref: ModelRef) -> str:
    return f"{ref.provider_id}/{ref.model_id}"


def _required_capabilities(
    payload: PreferencesPayload,
) -> list[tuple[str, ModelRef, str]]:
    """(label, ref, capability) triples that must hold for this configuration."""
    needs: list[tuple[str, ModelRef, str]] = []
    if payload.default_model_ref:
        needs.append(("默认主力模型", payload.default_model_ref, "tools"))
    if payload.default_vision_model_ref:
        needs.append(("默认视觉模型", payload.default_vision_model_ref, "vision"))
    for scene, binding in payload.slot_bindings.items():
        capability = (
            "vision"
            if scene in VISION_SCENES
            else "tools"
            if scene in TOOL_SCENES
            else None
        )
        if capability is None:
            continue
        for ref in [binding.model_ref, *binding.fallback_chain]:
            needs.append((f"场景「{scene}」", ref, capability))
    return needs


def _resolve_capabilities(
    session: Session,
    user_uid: str,
    refs: list[ModelRef],
    gateway: AiGatewayClient,
) -> dict[str, dict[str, bool]]:
    resolved: dict[str, dict[str, bool]] = {}
    unknown: list[ModelRef] = []
    for ref in refs:
        row = session.exec(
            select(UserCustomModel).where(
                UserCustomModel.user_uid == user_uid,
                UserCustomModel.provider_id == ref.provider_id,
                UserCustomModel.model_id == ref.model_id,
            )
        ).first()
        if row is not None:
            resolved[_capability_key(ref)] = {
                "vision": row.supports_vision,
                "tools": row.supports_tools,
                "reasoning": row.supports_reasoning,
            }
        else:
            unknown.append(ref)
    if unknown:
        try:
            builtin = gateway.get_builtin_capabilities(
                [ref.model_dump() for ref in unknown]
            )
        except AiGatewayUnavailableError as exc:
            raise ModelConfigError(
                503, "AI 服务暂时不可用，请稍后重试", "INTERNAL_SERVICE_UNAVAILABLE"
            ) from exc
        resolved.update(builtin)
    return resolved


def validate_preferences(
    session: Session,
    user: User,
    payload: PreferencesPayload,
    gateway: AiGatewayClient,
) -> None:
    for scene in payload.slot_bindings:
        if scene in ADMIN_ONLY_SCENES and user.role != "admin":
            raise ModelConfigError(403, f"场景「{scene}」仅管理员可配置")
    needs = _required_capabilities(payload)
    if not needs:
        return
    capabilities = _resolve_capabilities(
        session, user.uid, [ref for _, ref, _ in needs], gateway
    )
    labels = {"vision": "视觉理解", "tools": "工具调用"}
    for label, ref, capability in needs:
        known = capabilities.get(_capability_key(ref))
        if known is None:
            raise ModelConfigError(422, f"{label}引用的模型 {ref.model_id} 不存在")
        if not known.get(capability, False):
            raise ModelConfigError(
                422,
                f"{label}需要具备{labels[capability]}能力的模型，"
                f"{ref.model_id} 不满足，请更换模型",
                "MODEL_CAPABILITY_MISMATCH",
            )


def save_preferences(
    session: Session, user_uid: str, payload: PreferencesPayload
) -> UserModelPreferences:
    row = session.get(UserModelPreferences, user_uid) or UserModelPreferences(
        user_uid=user_uid
    )
    row.config_mode = payload.config_mode
    row.default_model_ref = (
        payload.default_model_ref.model_dump() if payload.default_model_ref else None
    )
    row.default_vision_model_ref = (
        payload.default_vision_model_ref.model_dump()
        if payload.default_vision_model_ref
        else None
    )
    row.default_thinking_level = payload.default_thinking_level
    row.runtime_options = payload.runtime_options.model_dump(exclude_none=True)
    row.slot_bindings = {
        scene: binding.model_dump() for scene, binding in payload.slot_bindings.items()
    }
    row.updated_at = _now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def apply_quick_switch(
    session: Session,
    user: User,
    payload: QuickSwitchPayload,
    gateway: AiGatewayClient,
) -> UserModelPreferences:
    row = session.get(UserModelPreferences, user.uid)
    current = _preferences_view(row)
    updated = PreferencesPayload(
        **current.model_dump(exclude={"updated_at"}),
    )
    if payload.model_ref is not None:
        updated.default_model_ref = payload.model_ref
        if (
            updated.config_mode == "advanced"
            and "chat_profile" in updated.slot_bindings
        ):
            binding = updated.slot_bindings["chat_profile"]
            binding.model_ref = payload.model_ref
    if payload.thinking_level is not None:
        updated.default_thinking_level = payload.thinking_level
        if (
            updated.config_mode == "advanced"
            and "chat_profile" in updated.slot_bindings
        ):
            updated.slot_bindings[
                "chat_profile"
            ].thinking_level = payload.thinking_level
    validate_preferences(session, user, updated, gateway)
    return save_preferences(session, user.uid, updated)


# -------------------------------------------------------------------- usage


def record_usage(
    session: Session, user_uid: str, payload: UsageRecordPayload
) -> UserModelUsageLog:
    row = UserModelUsageLog(
        usage_id=_new_id(), user_uid=user_uid, **payload.model_dump()
    )
    row.created_at = _now()
    session.add(row)
    session.commit()
    return row


def usage_summary(session: Session, user_uid: str, days: int) -> UsageSummary:
    since = _now() - timedelta(days=days)
    day = func.to_char(UserModelUsageLog.created_at, "YYYY-MM-DD")
    statement = (
        select(
            day,
            UserModelUsageLog.scene,
            func.count(),
            func.count().filter(UserModelUsageLog.success.is_(True)),
            func.coalesce(func.sum(UserModelUsageLog.input_tokens), 0),
            func.coalesce(func.sum(UserModelUsageLog.output_tokens), 0),
            func.coalesce(func.sum(UserModelUsageLog.cache_read_tokens), 0),
            func.coalesce(func.sum(UserModelUsageLog.cache_write_tokens), 0),
            func.coalesce(func.sum(UserModelUsageLog.reasoning_tokens), 0),
            func.coalesce(func.sum(UserModelUsageLog.estimated_cost_usd), 0.0),
            func.coalesce(func.avg(UserModelUsageLog.latency_ms), 0.0),
        )
        .where(UserModelUsageLog.user_uid == user_uid)
        .where(UserModelUsageLog.created_at >= since)
        .group_by(day, UserModelUsageLog.scene)
        .order_by(day, UserModelUsageLog.scene)
    )
    buckets = [
        UsageBucket(
            date=row[0],
            scene=row[1],
            requests=int(row[2]),
            success_requests=int(row[3]),
            input_tokens=int(row[4]),
            output_tokens=int(row[5]),
            cache_read_tokens=int(row[6]),
            cache_write_tokens=int(row[7]),
            reasoning_tokens=int(row[8]),
            estimated_cost_usd=float(row[9]),
            avg_latency_ms=float(row[10]),
        )
        for row in session.exec(statement).all()
    ]
    return UsageSummary(
        days=days,
        buckets=buckets,
        total_requests=sum(b.requests for b in buckets),
        total_tokens=sum(
            b.input_tokens + b.output_tokens + b.reasoning_tokens for b in buckets
        ),
        total_cost_usd=round(sum(b.estimated_cost_usd for b in buckets), 8),
    )


# ------------------------------------------------------ internal (decrypted)


def runtime_config(
    session: Session, user_uid: str, cipher: SecretCipher
) -> dict[str, Any]:
    user = session.exec(select(User).where(User.uid == user_uid)).first()
    providers: list[dict[str, Any]] = []
    for row in session.exec(
        select(UserModelProvider).where(UserModelProvider.user_uid == user_uid)
    ).all():
        entry: dict[str, Any] = {
            "provider_id": row.provider_id,
            "display_name": row.display_name,
            "is_builtin": row.is_builtin,
            "protocol": row.protocol,
            "base_url": row.base_url,
            "headers": _decrypt_headers(row, cipher),
            "auth_type": row.auth_type,
            "enabled": row.enabled,
            "api_key": None,
            "oauth_credential": None,
            "oauth_refresh_fingerprint": None,
            "oauth_expires_at": row.oauth_expires_at,
        }
        if row.secret_encrypted:
            secret = cipher.decrypt(row.secret_encrypted)
            if row.auth_type == "oauth":
                entry["oauth_credential"] = json.loads(secret)
                entry["oauth_refresh_fingerprint"] = fingerprint(
                    cipher.decrypt(row.oauth_refresh_encrypted)
                    if row.oauth_refresh_encrypted
                    else None
                )
            else:
                entry["api_key"] = secret
        providers.append(entry)
    models = session.exec(
        select(UserCustomModel).where(UserCustomModel.user_uid == user_uid)
    ).all()
    return {
        "user_uid": user_uid,
        "role": user.role if user else None,
        "providers": providers,
        "custom_models": [
            custom_model_view(row).model_dump(mode="json") for row in models
        ],
        "preferences": _preferences_view(
            session.get(UserModelPreferences, user_uid)
        ).model_dump(mode="json"),
    }


def save_oauth_credential(
    session: Session,
    user_uid: str,
    provider_id: str,
    credential: dict,
    expires_at: datetime | None,
    account_label: str | None,
    cipher: SecretCipher,
) -> None:
    row = _get_provider(session, user_uid, provider_id, for_update=True)
    if row is None:
        row = UserModelProvider(
            id=_new_id(),
            user_uid=user_uid,
            provider_id=provider_id,
            display_name=provider_id,
            is_builtin=True,
        )
    row.auth_type = "oauth"
    _write_oauth(row, credential, expires_at, account_label, cipher)
    session.add(row)
    session.commit()


def _write_oauth(
    row: UserModelProvider,
    credential: dict,
    expires_at: datetime | None,
    account_label: str | None,
    cipher: SecretCipher,
) -> None:
    row.secret_encrypted = cipher.encrypt(json.dumps(credential, ensure_ascii=False))
    refresh = credential.get("refresh")
    row.oauth_refresh_encrypted = cipher.encrypt(str(refresh)) if refresh else None
    row.oauth_expires_at = expires_at.replace(tzinfo=None) if expires_at else None
    if account_label:
        row.oauth_account_label = account_label
    row.updated_at = _now()


def oauth_refresh_lock(
    session: Session,
    user_uid: str,
    provider_id: str,
    previous_fingerprint: str | None,
    new_credential: dict | None,
    expires_at: datetime | None,
    cipher: SecretCipher,
) -> dict[str, Any]:
    """Row-locked compare-and-swap so concurrent refreshes cannot clobber each other."""
    row = _get_provider(session, user_uid, provider_id, for_update=True)
    if row is None or row.auth_type != "oauth" or not row.secret_encrypted:
        session.rollback()
        raise ModelConfigError(404, "该 Provider 尚未完成 OAuth 授权")
    current_refresh = (
        cipher.decrypt(row.oauth_refresh_encrypted)
        if row.oauth_refresh_encrypted
        else None
    )
    current_fingerprint = fingerprint(current_refresh)
    outcome = "unchanged"
    if new_credential is not None:
        if (
            previous_fingerprint is not None
            and previous_fingerprint != current_fingerprint
        ):
            outcome = "conflict"
        else:
            _write_oauth(row, new_credential, expires_at, None, cipher)
            session.add(row)
            outcome = "refreshed"
            current_refresh = new_credential.get("refresh")
            current_fingerprint = fingerprint(
                str(current_refresh) if current_refresh else None
            )
    session.commit()
    session.refresh(row)
    return {
        "outcome": outcome,
        "credential": json.loads(cipher.decrypt(row.secret_encrypted)),
        "refresh_fingerprint": current_fingerprint,
        "expires_at": row.oauth_expires_at,
    }
