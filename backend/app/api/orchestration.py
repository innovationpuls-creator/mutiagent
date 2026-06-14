from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, Callable, Generator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, messages_from_dict, messages_to_dict
from sqlmodel import Session

from app.core.security import create_get_current_user
from app.models import User, UserProfile
from app.orchestration.agents.profile import is_complete_profile_data
from app.orchestration.graph import build_orchestration_graph, stream_orchestration_events
from app.orchestration.rule_engine import (
    is_navigation_query,
    is_course_outline_regeneration_query,
    is_course_start_query,
    is_review_plan_query,
    parse_leaf_regeneration_pending_marker,
    parse_leaf_resource_generation_request,
)
from app.schemas import (
    ChatMessageRequest,
    ChatResponse,
    ChatStartRequest,
    SessionStateResponse,
)
from app.services.course_generation_status_service import (
    finish_course_generation,
    start_course_generation,
)

SessionDependency = Callable[[], Generator[Session, None, None]]


def _completed_user_profile(session: Session, user_uid: str) -> dict | None:
    profile = session.get(UserProfile, user_uid)
    if profile is None:
        return None
    profile_data = profile.profile_data if isinstance(profile.profile_data, dict) else None
    if not is_complete_profile_data(profile_data):
        return None
    return profile_data


def _load_owned_session(session: Session, session_id: str, user_uid: str):
    from app.services.conversation_session_service import load_session

    conv_session = load_session(session, session_id)
    if conv_session is None or conv_session.user_uid != user_uid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return conv_session


def _stream_error_message(session: Session, session_id: str, user_uid: str, exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        return "对话请求失败，请稍后重试。"

    from app.services.conversation_session_service import load_session

    conv_session = load_session(session, session_id)
    if conv_session is None or conv_session.user_uid != user_uid:
        return "会话不存在"

    return str(exc) or "对话请求失败，请稍后重试。"


def _append_turn_with_user_fallback(
    session: Session,
    session_id: str,
    current_user_message: HumanMessage,
    completed_text: str,
) -> None:
    from app.services.conversation_session_service import append_messages

    try:
        append_messages(
            session,
            session_id,
            messages_to_dict([current_user_message, AIMessage(content=completed_text)]),
        )
    except Exception:
        try:
            append_messages(
                session,
                session_id,
                messages_to_dict([current_user_message]),
            )
        except Exception:
            pass
        raise


def _append_user_message_safely(
    session: Session,
    session_id: str,
    current_user_message: HumanMessage,
) -> None:
    from app.services.conversation_session_service import append_messages

    try:
        append_messages(
            session,
            session_id,
            messages_to_dict([current_user_message]),
        )
    except Exception:
        pass


def _sse(event: str, payload: dict) -> str:
    """Format an SSE event with fine-grained event types."""
    if event == "message":
        payload["type"] = payload.get("type", event)
        return f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _memory_event(
    step_id: str,
    message: str,
    *,
    success: bool | None = None,
    summary: str | None = None,
) -> dict:
    payload: dict[str, object] = {
        "stepId": step_id,
        "kind": "system",
        "agent": "memory_agent",
        "label": "记忆智能体",
    }
    if success is None:
        payload["message"] = message
        return payload
    payload["success"] = success
    payload["summary"] = summary or message
    return payload


def _is_course_resource_generation_query(query: str) -> bool:
    from app.orchestration.rule_engine import is_course_resource_generation_query

    return is_course_resource_generation_query(query)


def _is_outline_review_query(query: str) -> bool:
    text = query.strip()
    if _is_course_resource_generation_query(text):
        return False
    return "大纲" in text and ("课" in text or "课程" in text)


def _is_learning_path_review_query(query: str) -> bool:
    return is_review_plan_query(query)


def _current_course_id_from_paths(year_paths: dict[str, dict]) -> str:
    from app.services.learning_path_service import get_current_course_id_from_year_learning_paths

    return get_current_course_id_from_year_learning_paths(year_paths)


def _grade_name_from_path(year: str, path: dict) -> str:
    grade_plans = path.get("grade_plans")
    if isinstance(grade_plans, dict):
        grade_plan = grade_plans.get(year)
        if isinstance(grade_plan, dict):
            grade_name = grade_plan.get("grade_name")
            if isinstance(grade_name, str) and grade_name.strip():
                return grade_name.strip()
    grade_name = path.get("grade_name")
    if isinstance(grade_name, str) and grade_name.strip():
        return grade_name.strip()
    return year


def _course_nodes_from_path(year: str, path: dict) -> list[dict]:
    from app.services.learning_path_service import get_grade_courses

    grade_plans = path.get("grade_plans")
    if isinstance(grade_plans, dict):
        return get_grade_courses(path, year)

    courses = path.get("courses")
    if isinstance(courses, list):
        return [course for course in courses if isinstance(course, dict)]
    return []


def _course_title(course: dict) -> str:
    for key in ("course_or_chapter_theme", "course_name", "title"):
        value = course.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    course_id = course.get("course_node_id") or course.get("course_id")
    return str(course_id).strip() if course_id else "未命名课程"


def _format_learning_path_text(year_paths: dict[str, dict], latest_grade_year: str = "") -> str:
    from app.services.learning_path_service import YEAR_ORDER

    lines = ["你的学习路径里已经有这些课程："]
    ordered_years = [year for year in YEAR_ORDER if year in year_paths]
    ordered_years.extend(year for year in year_paths if year not in ordered_years)
    for year in ordered_years:
        path = year_paths.get(year)
        if not isinstance(path, dict):
            continue
        grade_name = _grade_name_from_path(year, path)
        courses = _course_nodes_from_path(year, path)
        lines.append(f"{grade_name}（{year}）：{len(courses)} 门课")
        for index, course in enumerate(courses, start=1):
            title = _course_title(course)
            goal = course.get("course_goal")
            suffix = f"：{goal.strip()}" if isinstance(goal, str) and goal.strip() else ""
            lines.append(f"{index}. {title}{suffix}")

    from app.services.learning_path_service import get_current_course_id_from_year_learning_paths

    current_course_id = get_current_course_id_from_year_learning_paths(year_paths, latest_grade_year)
    if current_course_id:
        lines.append(f"当前学习节点：{current_course_id}")
    return "\n".join(lines)


def _chapter_prefix(section_id: str) -> str:
    numbers = {
        "1": "第一章",
        "2": "第二章",
        "3": "第三章",
        "4": "第四章",
        "5": "第五章",
        "6": "第六章",
        "7": "第七章",
        "8": "第八章",
        "9": "第九章",
        "10": "第十章",
        "11": "第十一章",
        "12": "第十二章",
    }
    return numbers.get(section_id, f"第{section_id}章")


def _section_display_title(section: dict) -> str:
    title = section.get("title")
    section_id = section.get("section_id")
    if not isinstance(title, str) or not title.strip():
        return ""
    if not isinstance(section_id, str) or "." in section_id:
        if isinstance(section_id, str) and section_id.strip():
            sid = section_id.strip()
            t = title.strip()
            if t.startswith(f"{sid} ") or t.startswith(f"{sid}　") or t == sid:
                return t
            return f"{sid} {t}"
        return title.strip()
    if title.startswith("第"):
        return title.strip()
    return f"{_chapter_prefix(section_id)}：{title.strip()}"


def _format_course_outline_text(course_knowledge: dict) -> str:
    course_name = str(course_knowledge.get("course_name", "")).strip()
    grade_year = str(course_knowledge.get("grade_year", "")).strip()
    lines = [f"课程大纲 · {grade_year}".strip(), course_name]
    summary = course_knowledge.get("personalization_summary")
    if isinstance(summary, str) and summary.strip():
        lines.extend(["", "个性化安排", summary.strip()])

    learning_sequence = course_knowledge.get("learning_sequence")
    if isinstance(learning_sequence, list) and learning_sequence:
        lines.extend(["", "推荐学习步骤"])
        lines.extend(str(item).strip() for item in learning_sequence if str(item).strip())

    sections = course_knowledge.get("sections")
    if isinstance(sections, list) and sections:
        lines.extend(["", "章节展开"])
        for section in sections:
            if not isinstance(section, dict):
                continue
            display_title = _section_display_title(section)
            if not display_title:
                continue
            description = section.get("description")
            if isinstance(description, str) and description.strip():
                lines.append(f"{display_title}：{description.strip()}")
            else:
                lines.append(display_title)
            key_points = section.get("key_knowledge_points")
            if isinstance(key_points, list):
                joined_points = "、".join(str(item).strip() for item in key_points if str(item).strip())
                if joined_points:
                    lines.append(f"核心知识点：{joined_points}")

    section_markdowns = course_knowledge.get("section_markdowns")
    if isinstance(section_markdowns, dict) and section_markdowns:
        lines.extend(["", "已生成教学文档"])
        lines.extend(sorted(str(section_id) for section_id in section_markdowns.keys()))

    section_video_links = course_knowledge.get("section_video_links")
    if isinstance(section_video_links, dict) and section_video_links:
        lines.extend(["", "已生成视频资源"])
        lines.extend(sorted(str(section_id) for section_id in section_video_links.keys()))

    section_html_animations = course_knowledge.get("section_html_animations")
    if isinstance(section_html_animations, dict) and section_html_animations:
        lines.extend(["", "已生成动画资源"])
        lines.extend(sorted(str(section_id) for section_id in section_html_animations.keys()))
    return "\n".join(line for line in lines if line is not None)


def _format_course_next_step_text(course_knowledge: dict) -> str:
    course_name = str(course_knowledge.get("course_name", "")).strip() or "当前课程"
    sections = course_knowledge.get("sections")
    first_section_title = ""
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            parent_section_id = section.get("parent_section_id")
            depth = section.get("depth")
            if parent_section_id is not None and depth != 1:
                continue
            first_section_title = _section_display_title(section)
            if first_section_title:
                break

    target = f"的{first_section_title}" if first_section_title else ""
    return "\n".join([
        f"下一步：进入《{course_name}》{target}。",
        "先生成第一章教学内容，再按小节完成练习与检查点。",
        "直接发送：开始学习这门课",
    ])


async def _stream_chat_events(
    session_id: str,
    user_uid: str,
    user_message: str,
    db_session: Session,
    payload: ChatMessageRequest | None = None,
) -> AsyncGenerator[str, None]:
    """SSE generator: load context from DB, run graph, stream events."""
    from app.services.profile_service import get_user_profile
    from app.services.learning_path_service import (
        get_all_year_learning_paths,
        get_current_course_id_from_year_learning_paths,
        get_latest_grade_year,
    )
    from app.services.course_knowledge_service import (
        get_user_course_knowledge_outline,
    )
    try:
        conv_session = _load_owned_session(db_session, session_id, user_uid)
        yield _sse("session_started", {"session_id": session_id, "query": user_message})

        yield _sse("agent_calling", _memory_event("memory-history-load", "正在读取历史对话记录"))
        raw_history_messages = conv_session.messages or []
        chat_message_dicts = [
            m for m in raw_history_messages
            if not (isinstance(m, dict) and m.get("type") == "learning_path_intake")
        ]
        history_messages = messages_from_dict(chat_message_dicts) if chat_message_dicts else []
        yield _sse(
            "agent_result",
            _memory_event(
                "memory-history-load",
                "历史对话记录已装入本轮上下文",
                success=True,
                summary="历史对话记录已装入本轮上下文",
            ),
        )

        yield _sse("agent_calling", _memory_event("memory-profile-load", "正在提取用户画像数据"))
        profile = get_user_profile(db_session, user_uid)
        yield _sse(
            "agent_result",
            _memory_event(
                "memory-profile-load",
                "用户画像数据已提取",
                success=True,
                summary="用户画像数据已提取",
            ),
        )

        yield _sse("agent_calling", _memory_event("memory-path-load", "正在提取学习路径数据"))
        year_paths = get_all_year_learning_paths(db_session, user_uid)
        latest_grade_year = get_latest_grade_year(db_session, user_uid)
        yield _sse(
            "agent_result",
            _memory_event(
                "memory-path-load",
                "学习路径数据已提取",
                success=True,
                summary="学习路径数据已提取",
            ),
        )

        yield _sse("agent_calling", _memory_event("memory-outline-load", "正在提取课程大纲数据"))
        current_course_id = get_current_course_id_from_year_learning_paths(year_paths, latest_grade_year)
        course_knowledge = (
            get_user_course_knowledge_outline(db_session, user_uid, current_course_id)
            if current_course_id
            else None
        )
        yield _sse(
            "agent_result",
            _memory_event(
                "memory-outline-load",
                "课程大纲数据已提取",
                success=True,
                summary="课程大纲数据已提取",
            ),
        )

        if profile and current_course_id:
            from app.models import ChapterWeakness
            from sqlmodel import select
            stmt = select(ChapterWeakness).where(
                ChapterWeakness.user_uid == user_uid,
                ChapterWeakness.course_node_id == current_course_id,
                ChapterWeakness.consumed == False,
            )
            unconsumed = db_session.exec(stmt).all()
            if unconsumed:
                kp_names = list(dict.fromkeys(w.knowledge_point_name for w in unconsumed if w.knowledge_point_name))
                if kp_names:
                    orig_weaknesses = profile.get("weaknesses", "")
                    weakness_suffix = f"[Adaptive Weaknesses] Recently struggled with: {', '.join(kp_names)}"
                    if orig_weaknesses:
                        profile["weaknesses"] = f"{orig_weaknesses}\n{weakness_suffix}"
                    else:
                        profile["weaknesses"] = weakness_suffix

        if payload and getattr(payload, "image_attachment", None):
            current_user_message = HumanMessage(
                content=[
                    {"type": "text", "text": user_message},
                    {"type": "image_url", "image_url": {"url": payload.image_attachment}}
                ]
            )
        else:
            current_user_message = HumanMessage(content=user_message)

        state = {
            "user_id": user_uid,
            "session_id": session_id,
            "query": user_message,
            "messages": [*history_messages, current_user_message],
        }

        if profile:
            state["profile"] = profile
        from app.services.conversation_session_service import latest_learning_path_intake
        intake = latest_learning_path_intake(raw_history_messages)
        if intake:
            state["learning_path_intake"] = intake
        if year_paths:
            state["year_learning_paths"] = year_paths
        if latest_grade_year:
            state["latest_grade_year"] = latest_grade_year
        if course_knowledge:
            state["course_knowledge"] = course_knowledge

        yield _sse(
            "agent_result",
            _memory_event(
                "memory-context-load",
                "历史对话、用户画像、学习路径与课程大纲已完成状态组装",
                success=True,
                summary="历史对话、用户画像、学习路径与课程大纲已完成状态组装",
            ),
        )

        generation_request = parse_leaf_resource_generation_request(user_message)
        if generation_request is None:
            latest_ai = ""
            for message in reversed(history_messages):
                content = getattr(message, "content", "")
                if isinstance(content, str) and content.strip():
                    latest_ai = content.strip()
                    break
            pending_regeneration = parse_leaf_regeneration_pending_marker(latest_ai)
            if pending_regeneration is not None:
                generation_request = {
                    "course_node_id": pending_regeneration["course_node_id"],
                    "chapter_section_id": pending_regeneration["chapter_section_id"],
                    "scope": "chapter_sections",
                    "mode": "regenerate",
                }

        if generation_request is not None:
            from app.orchestration.agents.course_resources import stream_chapter_resource_generation
            from app.orchestration.llm import get_search_worker_llm, get_worker_llm
            from app.services.forest_service import chapter_generation_is_available

            requested_course_id = generation_request["course_node_id"]
            requested_chapter_id = generation_request["chapter_section_id"]
            current_course_id = get_current_course_id_from_year_learning_paths(year_paths, latest_grade_year)
            if requested_course_id != current_course_id:
                completed_text = "只能为当前课程生成教学内容。"
                _append_turn_with_user_fallback(db_session, session_id, current_user_message, completed_text)
                yield _sse("message_completed", {"full_text": completed_text})
                yield _sse(
                    "session_completed",
                    {
                        "session_id": session_id,
                        "has_profile": is_complete_profile_data(profile),
                        "has_paths": bool(year_paths),
                        "has_outline": bool(course_knowledge),
                    },
                )
                return
            if not chapter_generation_is_available(
                db_session,
                user_uid,
                requested_course_id,
                requested_chapter_id,
                course_knowledge,
            ):
                completed_text = "通过章节测验后会开放下一章内容生成。"
                _append_turn_with_user_fallback(db_session, session_id, current_user_message, completed_text)
                yield _sse("message_completed", {"full_text": completed_text})
                yield _sse(
                    "session_completed",
                    {
                        "session_id": session_id,
                        "has_profile": is_complete_profile_data(profile),
                        "has_paths": bool(year_paths),
                        "has_outline": bool(course_knowledge),
                    },
                )
                return
            composed = course_knowledge.get("section_composed_markdowns") if isinstance(course_knowledge, dict) else None
            if generation_request["mode"] == "generate" and isinstance(composed, dict) and composed:
                completed_text = (
                    "重新生成本章前，请告诉我下一版需要侧重哪里。\n\n"
                    "[LEAF_REGEN_PENDING]\n"
                    f"course_node_id: {requested_course_id}\n"
                    f"chapter_section_id: {requested_chapter_id}\n"
                    "[/LEAF_REGEN_PENDING]"
                )
                _append_turn_with_user_fallback(db_session, session_id, current_user_message, completed_text)
                yield _sse("message_completed", {"full_text": completed_text})
                yield _sse(
                    "session_completed",
                    {
                        "session_id": session_id,
                        "has_profile": is_complete_profile_data(profile),
                        "has_paths": bool(year_paths),
                        "has_outline": bool(course_knowledge),
                    },
                )
                return

            try:
                start_course_generation(user_uid, requested_course_id, requested_chapter_id)
            except ValueError as exc:
                yield _sse("error", {
                    "message": str(exc),
                    "recoverable": True,
                    "course_id": requested_course_id,
                    "chapter_section_id": requested_chapter_id,
                    "kind": "course_resource_chapter",
                    "phase": "generation_status",
                    "status": "error",
                })
                return
            had_resource_error = False
            try:
                async for event in stream_chapter_resource_generation(
                    state,
                    get_worker_llm(),
                    get_search_worker_llm(),
                    course_id=requested_course_id,
                    chapter_section_id=requested_chapter_id,
                    regeneration_focus=user_message if generation_request["mode"] == "regenerate" else "",
                ):
                    event_name = str(event.get("event", "message"))
                    payload = {k: v for k, v in event.items() if k != "event"}
                    if event_name == "error":
                        had_resource_error = True
                        payload.setdefault("course_id", requested_course_id)
                        payload.setdefault("chapter_section_id", requested_chapter_id)
                        payload.setdefault("kind", "course_resource_chapter")
                        payload.setdefault("status", "error")
                        yield _sse(event_name, payload)
                        break
                    yield _sse(event_name, payload)
            finally:
                finish_course_generation(user_uid, requested_course_id, requested_chapter_id)
            if had_resource_error:
                _append_user_message_safely(db_session, session_id, current_user_message)
                return
            _append_turn_with_user_fallback(
                db_session,
                session_id,
                current_user_message,
                "本章教学内容已生成。",
            )
            return

        if course_knowledge and is_navigation_query(user_message):
            completed_text = _format_course_next_step_text(course_knowledge)
            _append_turn_with_user_fallback(
                db_session,
                session_id,
                current_user_message,
                completed_text,
            )
            yield _sse("message_completed", {"full_text": completed_text})
            yield _sse(
                "session_completed",
                {
                    "session_id": session_id,
                    "has_profile": is_complete_profile_data(profile),
                    "has_paths": bool(year_paths),
                    "has_outline": True,
                },
            )
            return

        if course_knowledge and (
            (_is_outline_review_query(user_message) and not is_course_outline_regeneration_query(user_message))
            or is_course_start_query(user_message)
        ):
            completed_text = _format_course_outline_text(course_knowledge)
            yield _sse(
                "data_update",
                {
                    "update_type": "course_knowledge_loaded",
                    "label": "课程大纲",
                    "course_id": course_knowledge.get("course_id", ""),
                    "grade_year": course_knowledge.get("grade_year", ""),
                    "summary": "已从数据库读取课程大纲",
                },
            )
            _append_turn_with_user_fallback(
                db_session,
                session_id,
                current_user_message,
                completed_text,
            )
            yield _sse("message_completed", {"full_text": completed_text})
            yield _sse(
                "session_completed",
                {
                    "session_id": session_id,
                    "has_profile": is_complete_profile_data(profile),
                    "has_paths": bool(year_paths),
                    "has_outline": True,
                },
            )
            return

        if year_paths and _is_learning_path_review_query(user_message):
            completed_text = _format_learning_path_text(year_paths, latest_grade_year)
            yield _sse(
                "data_update",
                {
                    "update_type": "learning_path_loaded",
                    "label": "学习路径",
                    "years": list(year_paths.keys()),
                    "summary": "已从数据库读取学习路径",
                },
            )
            _append_turn_with_user_fallback(
                db_session,
                session_id,
                current_user_message,
                completed_text,
            )
            yield _sse("message_completed", {"full_text": completed_text})
            yield _sse(
                "session_completed",
                {
                    "session_id": session_id,
                    "has_profile": is_complete_profile_data(profile),
                    "has_paths": True,
                    "has_outline": bool(course_knowledge),
                },
            )
            return

        completed_text = ""
        had_error = False
        completed_event_payload: dict | None = None
        session_completed_payload: dict | None = None
        try:
            async for event in stream_orchestration_events(state):
                event_name = str(event.get("event", "message"))
                if event_name == "message_completed":
                    completed_text = str(event.get("full_text", ""))
                    completed_event_payload = {k: v for k, v in event.items() if k != "event"}
                    continue
                if event_name == "session_completed":
                    session_completed_payload = {k: v for k, v in event.items() if k != "event"}
                    continue
                if event_name == "error":
                    had_error = True
                if event_name in {"session_started"}:
                    continue
                if event_name in {"text_chunk", "supervisor_thinking", "supervisor_plan"}:
                    payload = {k: v for k, v in event.items() if k != "event"}
                    yield _sse("message", {**payload, "type": event_name})
                else:
                    payload = {k: v for k, v in event.items() if k != "event"}
                    yield _sse(event_name, payload)
            new_messages = [current_user_message]
            if completed_text and not had_error:
                new_messages.append(AIMessage(content=completed_text))
            from app.services.conversation_session_service import append_messages
            append_messages(db_session, session_id, messages_to_dict(new_messages))
            if completed_event_payload is not None:
                yield _sse("message_completed", completed_event_payload)
            if session_completed_payload is not None:
                yield _sse("session_completed", session_completed_payload)
        except Exception as exc:
            _append_user_message_safely(
                db_session,
                session_id,
                current_user_message,
            )
            yield _sse("error", {
                "message": _stream_error_message(db_session, session_id, user_uid, exc),
                "recoverable": True,
            })
    except Exception as exc:
        yield _sse("error", {
            "message": _stream_error_message(db_session, session_id, user_uid, exc),
            "recoverable": True,
        })


def create_orchestration_router(session_dependency: SessionDependency) -> APIRouter:
    router = APIRouter(prefix="/api/chat", tags=["chat"])
    get_current_user = create_get_current_user(session_dependency)

    @router.post("/start", response_model=ChatResponse)
    async def start_chat(
        payload: ChatStartRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> ChatResponse:
        """Start a new chat session."""
        session_id = str(uuid.uuid4())

        from app.services.conversation_session_service import load_or_create_session
        load_or_create_session(session, session_id, current_user.uid)

        return ChatResponse(
            session_id=session_id,
            reply_text="你好！我是你的学习助手。请告诉我你的基本情况，比如年级、专业、想学什么？",
        )

    @router.post("/message")
    async def send_message(
        payload: ChatMessageRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> StreamingResponse:
        """Send a message and receive SSE-streamed agent responses."""
        _load_owned_session(session, payload.session_id, current_user.uid)

        return StreamingResponse(
            _stream_chat_events(
                session_id=payload.session_id,
                user_uid=current_user.uid,
                user_message=payload.message,
                db_session=session,
                payload=payload,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/sessions/{session_id}", response_model=SessionStateResponse)
    async def get_session_state(
        session_id: str,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> SessionStateResponse:
        """Get the current state of a chat session."""
        from app.services.conversation_session_service import load_session as load_conv
        from app.services.profile_service import get_user_profile
        from app.services.learning_path_service import (
            get_all_year_learning_paths,
            get_current_course_id_from_year_learning_paths,
            get_latest_grade_year,
        )
        from app.services.course_knowledge_service import (
            get_user_course_knowledge_outline,
        )

        conv = load_conv(session, session_id)
        if conv is None or conv.user_uid != current_user.uid:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

        profile = get_user_profile(session, current_user.uid)
        year_paths = get_all_year_learning_paths(session, current_user.uid)
        latest_grade_year = get_latest_grade_year(session, current_user.uid)
        current_course_id = get_current_course_id_from_year_learning_paths(
            year_paths,
            latest_grade_year,
        )
        course_knowledge = (
            get_user_course_knowledge_outline(session, current_user.uid, current_course_id)
            if current_course_id
            else None
        )

        return SessionStateResponse(
            session_id=session_id,
            user_uid=current_user.uid,
            messages=conv.messages or [],
            profile=profile,
            year_learning_paths=year_paths,
            latest_grade_year=latest_grade_year or None,
            course_knowledge=course_knowledge,
            updated_at=conv.updated_at,
        )

    return router
