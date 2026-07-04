from __future__ import annotations

import abc
import json
import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    messages_from_dict,
    messages_to_dict,
)

from app.orchestration.agents.profile import is_complete_profile_data
from app.orchestration.graph import stream_orchestration_events
from app.orchestration.rule_engine import (
    _is_learning_path_review_query,
    _is_outline_review_query,
    is_course_outline_regeneration_query,
    is_course_start_query,
    is_navigation_query,
    parse_leaf_regeneration_pending_marker,
    parse_leaf_resource_generation_request,
)
from app.services.course_generation_status_service import (
    finish_course_generation,
    start_course_generation,
)

if TYPE_CHECKING:
    from sqlmodel import Session

    from app.schemas import ChatMessageRequest

logger = logging.getLogger(__name__)


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
    """Helper to return standard memory loader payload."""
    evt = {
        "stepId": step_id,
        "kind": "memory_loader",
        "agent": "memory_loader",
        "label": "记忆提取",
        "message": message,
    }
    if success is not None:
        evt["success"] = success
    if summary is not None:
        evt["summary"] = summary
    return evt


class ChatContextLoader:
    """Loads necessary data context from DB and prepares standard OrchestrationState."""

    def __init__(
        self,
        db_session: Session,
        user_uid: str,
        session_id: str,
        user_message: str,
        payload: ChatMessageRequest | None = None,
    ) -> None:
        self.db_session = db_session
        self.user_uid = user_uid
        self.session_id = session_id
        self.user_message = user_message
        self.payload = payload
        self.state: dict[str, Any] = {}
        self.current_user_message: HumanMessage | None = None

    async def load(self) -> AsyncGenerator[str, None]:  # noqa: C901
        from app.api.orchestration import _load_owned_session
        from app.services.course_knowledge_service import (
            get_user_course_knowledge_outline,
        )
        from app.services.learning_path_service import (
            get_all_year_learning_paths,
            get_current_course_id_from_year_learning_paths,
            get_latest_grade_year,
        )
        from app.services.profile_service import get_user_profile

        conv_session = _load_owned_session(
            self.db_session, self.session_id, self.user_uid
        )

        yield _sse(
            "agent_calling",
            _memory_event("memory-history-load", "正在读取历史对话记录"),
        )
        raw_history_messages = conv_session.messages or []
        chat_message_dicts = [
            m
            for m in raw_history_messages
            if not (isinstance(m, dict) and m.get("type") == "learning_path_intake")
        ]
        history_messages = (
            messages_from_dict(chat_message_dicts) if chat_message_dicts else []
        )
        yield _sse(
            "agent_result",
            _memory_event(
                "memory-history-load",
                "历史对话记录已装入本轮上下文",
                success=True,
                summary="历史对话记录已装入本轮上下文",
            ),
        )

        yield _sse(
            "agent_calling",
            _memory_event("memory-profile-load", "正在提取用户画像数据"),
        )
        profile = get_user_profile(self.db_session, self.user_uid)
        yield _sse(
            "agent_result",
            _memory_event(
                "memory-profile-load",
                "用户画像数据已提取",
                success=True,
                summary="用户画像数据已提取",
            ),
        )

        yield _sse(
            "agent_calling", _memory_event("memory-path-load", "正在提取学习路径数据")
        )
        year_paths = get_all_year_learning_paths(self.db_session, self.user_uid)
        latest_grade_year = get_latest_grade_year(self.db_session, self.user_uid)
        yield _sse(
            "agent_result",
            _memory_event(
                "memory-path-load",
                "学习路径数据已提取",
                success=True,
                summary="学习路径数据已提取",
            ),
        )

        yield _sse(
            "agent_calling",
            _memory_event("memory-outline-load", "正在提取课程大纲数据"),
        )
        current_course_id = get_current_course_id_from_year_learning_paths(
            year_paths, latest_grade_year
        )
        course_knowledge = (
            get_user_course_knowledge_outline(
                self.db_session, self.user_uid, current_course_id
            )
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
            from sqlmodel import select

            from app.models import ChapterWeakness

            stmt = select(ChapterWeakness).where(
                ChapterWeakness.user_uid == self.user_uid,
                ChapterWeakness.course_node_id == current_course_id,
                ChapterWeakness.consumed.is_(False),
            )
            unconsumed = self.db_session.exec(stmt).all()
            if unconsumed:
                kp_names = list(
                    dict.fromkeys(
                        w.knowledge_point_name
                        for w in unconsumed
                        if w.knowledge_point_name
                    )
                )
                if kp_names:
                    orig_weaknesses = profile.get("weaknesses", "")
                    weakness_suffix = (
                        "[Adaptive Weaknesses] Recently struggled with: "
                        f"{', '.join(kp_names)}"
                    )
                    if orig_weaknesses:
                        profile["weaknesses"] = f"{orig_weaknesses}\n{weakness_suffix}"
                    else:
                        profile["weaknesses"] = weakness_suffix

        if self.payload and getattr(self.payload, "image_attachment", None):
            self.current_user_message = HumanMessage(
                content=[
                    {"type": "text", "text": self.user_message},
                    {
                        "type": "image_url",
                        "image_url": {"url": self.payload.image_attachment},
                    },
                ]
            )
        else:
            self.current_user_message = HumanMessage(content=self.user_message)

        state = {
            "user_id": self.user_uid,
            "session_id": self.session_id,
            "query": self.user_message,
            "messages": [*history_messages, self.current_user_message],
        }

        if profile:
            state["profile"] = profile
        from app.services.conversation_session_service import (
            latest_learning_path_intake,
        )

        intake = latest_learning_path_intake(raw_history_messages)
        if intake:
            state["learning_path_intake"] = intake
        if year_paths:
            state["year_learning_paths"] = year_paths
        if latest_grade_year:
            state["latest_grade_year"] = latest_grade_year
        if course_knowledge:
            state["course_knowledge"] = course_knowledge

        self.state = state

        yield _sse(
            "agent_result",
            _memory_event(
                "memory-context-load",
                "历史对话、用户画像、学习路径与课程大纲已完成状态组装",
                success=True,
                summary="历史对话、用户画像、学习路径与课程大纲已完成状态组装",
            ),
        )


class BaseChatHandler(abc.ABC):
    """Abstract Base Class for Chat Message Handlers."""

    def __init__(self, db_session: Session, user_uid: str, session_id: str) -> None:
        self.db_session = db_session
        self.user_uid = user_uid
        self.session_id = session_id

    @abc.abstractmethod
    def can_handle(self, user_message: str, state: dict[str, Any]) -> bool:
        pass

    @abc.abstractmethod
    async def handle(  # noqa: C901
        self,
        user_message: str,
        state: dict[str, Any],
        current_user_message: HumanMessage,
    ) -> AsyncGenerator[str, None]:
        pass


class ResourceGenerationHandler(BaseChatHandler):
    """Handles course/chapter resource generation requests."""

    def __init__(
        self,
        db_session: Session,
        user_uid: str,
        session_id: str,
        payload: ChatMessageRequest | None = None,
    ) -> None:
        super().__init__(db_session, user_uid, session_id)
        self.payload = payload

    def can_handle(self, user_message: str, state: dict[str, Any]) -> bool:
        # Detect generation requests or pending regeneration markers
        gen_req = parse_leaf_resource_generation_request(user_message)
        if gen_req is not None:
            return True

        # Fallback to check if previous AI message has LEAF_REGEN_PENDING marker
        messages = state.get("messages", [])
        history_messages = messages[:-1] if messages else []
        latest_ai = ""
        for message in reversed(history_messages):
            content = getattr(message, "content", "")
            if isinstance(content, str) and content.strip():
                latest_ai = content.strip()
                break
        return parse_leaf_regeneration_pending_marker(latest_ai) is not None

    async def handle(  # noqa: C901
        self,
        user_message: str,
        state: dict[str, Any],
        current_user_message: HumanMessage,
    ) -> AsyncGenerator[str, None]:
        from app.api.orchestration import (
            _append_turn_with_user_fallback,
            _append_user_message_safely,
        )
        from app.orchestration.agents.course_resources import (
            stream_chapter_resource_generation,
        )
        from app.orchestration.llm import get_search_worker_llm, get_worker_llm
        from app.services.course_knowledge_service import (
            get_user_course_knowledge_outline,
        )
        from app.services.forest_service import chapter_generation_is_available
        from app.services.knowledge_base_service import (
            require_student_visible_textbooks,
        )
        from app.services.learning_path_service import (
            get_current_course_id_from_year_learning_paths,
        )

        profile = state.get("profile")
        year_paths = state.get("year_learning_paths")
        latest_grade_year = state.get("latest_grade_year")
        course_knowledge = state.get("course_knowledge")

        # Parse request structure
        generation_request = parse_leaf_resource_generation_request(user_message)
        if generation_request is None:
            messages = state.get("messages", [])
            history_messages = messages[:-1] if messages else []
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

        assert generation_request is not None

        requested_course_id = generation_request["course_node_id"]
        requested_chapter_id = generation_request["chapter_section_id"]
        current_course_id = get_current_course_id_from_year_learning_paths(
            year_paths, latest_grade_year
        )

        if requested_course_id != current_course_id:
            completed_text = "只能为当前课程生成教学内容。"
            _append_turn_with_user_fallback(
                self.db_session, self.session_id, current_user_message, completed_text
            )
            yield _sse("message_completed", {"full_text": completed_text})
            yield _sse(
                "session_completed",
                {
                    "session_id": self.session_id,
                    "has_profile": is_complete_profile_data(profile),
                    "has_paths": bool(year_paths),
                    "has_outline": bool(course_knowledge),
                },
            )
            return

        if not chapter_generation_is_available(
            self.db_session,
            self.user_uid,
            requested_course_id,
            requested_chapter_id,
            course_knowledge,
        ):
            completed_text = "通过章节测验后会开放下一章内容生成。"
            _append_turn_with_user_fallback(
                self.db_session, self.session_id, current_user_message, completed_text
            )
            yield _sse("message_completed", {"full_text": completed_text})
            yield _sse(
                "session_completed",
                {
                    "session_id": self.session_id,
                    "has_profile": is_complete_profile_data(profile),
                    "has_paths": bool(year_paths),
                    "has_outline": bool(course_knowledge),
                },
            )
            return

        composed = (
            course_knowledge.get("section_composed_markdowns")
            if isinstance(course_knowledge, dict)
            else None
        )
        if (
            generation_request["mode"] == "generate"
            and isinstance(composed, dict)
            and composed
        ):
            completed_text = (
                "重新生成本章前，请告诉我下一版需要侧重哪里。\n\n"
                "[LEAF_REGEN_PENDING]\n"
                f"course_node_id: {requested_course_id}\n"
                f"chapter_section_id: {requested_chapter_id}\n"
                "[/LEAF_REGEN_PENDING]"
            )
            _append_turn_with_user_fallback(
                self.db_session, self.session_id, current_user_message, completed_text
            )
            yield _sse("message_completed", {"full_text": completed_text})
            yield _sse(
                "session_completed",
                {
                    "session_id": self.session_id,
                    "has_profile": is_complete_profile_data(profile),
                    "has_paths": bool(year_paths),
                    "has_outline": bool(course_knowledge),
                },
            )
            return

        try:
            outline = get_user_course_knowledge_outline(
                self.db_session, self.user_uid, requested_course_id
            )
            if not isinstance(outline, dict):
                raise ValueError("课程大纲不存在。")
            require_student_visible_textbooks(self.db_session, outline)
        except ValueError as exc:
            completed_text = str(exc)
            _append_turn_with_user_fallback(
                self.db_session, self.session_id, current_user_message, completed_text
            )
            yield _sse("message_completed", {"full_text": completed_text})
            yield _sse(
                "session_completed",
                {
                    "session_id": self.session_id,
                    "has_profile": is_complete_profile_data(profile),
                    "has_paths": bool(year_paths),
                    "has_outline": bool(course_knowledge),
                },
            )
            return

        try:
            start_course_generation(
                self.user_uid, requested_course_id, requested_chapter_id
            )
        except ValueError as exc:
            yield _sse(
                "error",
                {
                    "message": str(exc),
                    "recoverable": True,
                    "course_id": requested_course_id,
                    "chapter_section_id": requested_chapter_id,
                    "kind": "course_resource_chapter",
                    "phase": "generation_status",
                    "status": "error",
                },
            )
            return

        had_resource_error = False
        try:
            async for event in stream_chapter_resource_generation(
                state,
                get_worker_llm(),
                get_search_worker_llm(),
                course_id=requested_course_id,
                chapter_section_id=requested_chapter_id,
                regeneration_focus=user_message
                if generation_request["mode"] == "regenerate"
                else "",
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
            finish_course_generation(
                self.user_uid, requested_course_id, requested_chapter_id
            )

        if had_resource_error:
            _append_user_message_safely(
                self.db_session, self.session_id, current_user_message
            )
            return

        _append_turn_with_user_fallback(
            self.db_session,
            self.session_id,
            current_user_message,
            "本章教学内容已生成。",
        )


class NavigationQueryHandler(BaseChatHandler):
    """Handles progression status or navigation inquiries."""

    def can_handle(self, user_message: str, state: dict[str, Any]) -> bool:
        course_knowledge = state.get("course_knowledge")
        return bool(course_knowledge and is_navigation_query(user_message))

    async def handle(  # noqa: C901
        self,
        user_message: str,
        state: dict[str, Any],
        current_user_message: HumanMessage,
    ) -> AsyncGenerator[str, None]:
        from app.api.orchestration import (
            _append_turn_with_user_fallback,
            _format_course_next_step_text,
        )

        profile = state.get("profile")
        year_paths = state.get("year_learning_paths")
        course_knowledge = state.get("course_knowledge")

        completed_text = _format_course_next_step_text(course_knowledge)
        _append_turn_with_user_fallback(
            self.db_session,
            self.session_id,
            current_user_message,
            completed_text,
        )
        yield _sse("message_completed", {"full_text": completed_text})
        yield _sse(
            "session_completed",
            {
                "session_id": self.session_id,
                "has_profile": is_complete_profile_data(profile),
                "has_paths": bool(year_paths),
                "has_outline": True,
            },
        )


class OutlineReviewHandler(BaseChatHandler):
    """Handles course outline viewing and display requests."""

    def can_handle(self, user_message: str, state: dict[str, Any]) -> bool:
        course_knowledge = state.get("course_knowledge")
        return bool(
            course_knowledge
            and (
                (
                    _is_outline_review_query(user_message)
                    and not is_course_outline_regeneration_query(user_message)
                )
                or is_course_start_query(user_message)
            )
        )

    async def handle(
        self,
        user_message: str,
        state: dict[str, Any],
        current_user_message: HumanMessage,
    ) -> AsyncGenerator[str, None]:
        from app.api.orchestration import (
            _append_turn_with_user_fallback,
            _format_course_outline_text,
        )

        profile = state.get("profile")
        year_paths = state.get("year_learning_paths")
        course_knowledge = state.get("course_knowledge")

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
            self.db_session,
            self.session_id,
            current_user_message,
            completed_text,
        )
        yield _sse("message_completed", {"full_text": completed_text})
        yield _sse(
            "session_completed",
            {
                "session_id": self.session_id,
                "has_profile": is_complete_profile_data(profile),
                "has_paths": bool(year_paths),
                "has_outline": True,
            },
        )


class LearningPathReviewHandler(BaseChatHandler):
    """Handles learning path visualization requests."""

    def can_handle(self, user_message: str, state: dict[str, Any]) -> bool:
        year_paths = state.get("year_learning_paths")
        return bool(year_paths and _is_learning_path_review_query(user_message))

    async def handle(
        self,
        user_message: str,
        state: dict[str, Any],
        current_user_message: HumanMessage,
    ) -> AsyncGenerator[str, None]:
        from app.api.orchestration import (
            _append_turn_with_user_fallback,
            _format_learning_path_text,
        )

        profile = state.get("profile")
        year_paths = state.get("year_learning_paths")
        latest_grade_year = state.get("latest_grade_year")
        course_knowledge = state.get("course_knowledge")

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
            self.db_session,
            self.session_id,
            current_user_message,
            completed_text,
        )
        yield _sse("message_completed", {"full_text": completed_text})
        yield _sse(
            "session_completed",
            {
                "session_id": self.session_id,
                "has_profile": is_complete_profile_data(profile),
                "has_paths": True,
                "has_outline": bool(course_knowledge),
            },
        )


class StandardOrchestrationHandler(BaseChatHandler):
    """Fallback handler invoking the main supervisor state graph."""

    def can_handle(self, user_message: str, state: dict[str, Any]) -> bool:
        # Standard orchestrator is always ready as the default fallback
        return True

    async def handle(  # noqa: C901
        self,
        user_message: str,
        state: dict[str, Any],
        current_user_message: HumanMessage,
    ) -> AsyncGenerator[str, None]:
        from app.services.conversation_session_service import append_messages

        completed_text = ""
        had_error = False
        completed_event_payload: dict | None = None
        session_completed_payload: dict | None = None

        try:
            async for event in stream_orchestration_events(state):
                event_name = str(event.get("event", "message"))
                if event_name == "message_completed":
                    completed_text = str(event.get("full_text", ""))
                    completed_event_payload = {
                        k: v for k, v in event.items() if k != "event"
                    }
                    continue
                if event_name == "session_completed":
                    session_completed_payload = {
                        k: v for k, v in event.items() if k != "event"
                    }
                    continue
                if event_name == "error":
                    had_error = True
                if event_name in {"session_started"}:
                    continue
                if event_name in {
                    "text_chunk",
                    "supervisor_thinking",
                    "supervisor_plan",
                }:
                    payload = {k: v for k, v in event.items() if k != "event"}
                    yield _sse("message", {**payload, "type": event_name})
                else:
                    payload = {k: v for k, v in event.items() if k != "event"}
                    yield _sse(event_name, payload)

            new_messages = [current_user_message]
            if completed_text and not had_error:
                new_messages.append(AIMessage(content=completed_text))

            append_messages(
                self.db_session, self.session_id, messages_to_dict(new_messages)
            )
            if completed_event_payload is not None:
                yield _sse("message_completed", completed_event_payload)
            if session_completed_payload is not None:
                yield _sse("session_completed", session_completed_payload)
        except Exception as exc:
            from app.api.orchestration import (
                _append_user_message_safely,
                _stream_error_message,
            )

            _append_user_message_safely(
                self.db_session,
                self.session_id,
                current_user_message,
            )
            yield _sse(
                "error",
                {
                    "message": _stream_error_message(
                        self.db_session, self.session_id, self.user_uid, exc
                    ),
                    "recoverable": True,
                },
            )
