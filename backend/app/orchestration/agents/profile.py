from __future__ import annotations

import json
import logging
import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.messages import ToolMessage
from langchain_core.prompts import ChatPromptTemplate

from app.orchestration.grade_contract import is_supported_current_grade, unsupported_current_grade_error
from app.orchestration.agents.models import ProfileOutput
from app.orchestration.agents.prompts import PROFILE_AGENT_SYSTEM_PROMPT
from app.orchestration.agents.utils import extract_last_tool_call_args, extract_last_tool_call_id
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_COMMANDS = ("默认", "直接", "随便帮我填", "不确定的你随便帮我填", "帮我生成")
REQUIRED_CONFIRMED_INFO_KEYS = frozenset({
    "current_grade",
    "major",
    "learning_stage",
    "has_clear_goal",
    "learning_method_preference",
    "learning_pace_preference",
    "content_preference",
    "need_guidance",
    "knowledge_foundation",
    "strengths",
    "weaknesses",
    "experience",
    "short_term_goal",
    "long_term_goal",
    "weekly_available_time",
    "constraints",
})
UNKNOWN_VALUE = "未知"
DEFAULT_GRADE = "大三"
DEFAULT_MAJOR = "软件工程"
DEFAULT_TOPIC = "AI 应用开发"
GRADE_PATTERN = re.compile(r"(大[一二三四]|大[1234]|[一二三四]年级|研[一二三])")
SPLIT_PATTERN = re.compile(r"[，,、；;／/\s]+")
EXPLICIT_FIELD_SPLIT_PATTERN = re.compile(r"[，,、；;]+")
PACE_SEGMENTS = {"平时学习", "周末集中", "每天少量", "高强度冲刺"}
GREETING_SEGMENTS = frozenset({"你好"})
MAJOR_BLOCKED_TERMS = (
    "推荐",
    "画像",
    "看看",
    "什么",
    "现在",
    "个人",
    "方向",
    "目标",
    "下一步",
    "接下来",
    "然后",
    "路径",
    "课程",
)
LEARNING_METHOD_SEGMENTS = ("喜欢自己摸索", "自己摸索", "自主学习", "自学")
GOAL_SEGMENTS = ("找工作", "就业", "实习", "考研")
TOPIC_PREFIXES = ("想学习", "想学", "学习", "学")
TOPIC_BLOCKED_VALUES = frozenset({"", "路径", "学习路径", "课程", "画像", "什么", "下一步"})
EXPLICIT_PROFILE_FIELD_PREFIXES: dict[str, tuple[str, ...]] = {
    "current_grade": ("年级改成", "年级调整为", "当前年级改成", "当前年级调整为"),
    "major": ("专业改成", "专业调整为", "我的专业是", "专业是"),
    "short_term_goal": ("短期目标改成", "短期目标调整为"),
    "long_term_goal": ("长期目标改成", "长期目标调整为"),
    "weekly_available_time": ("每周可投入时间改成", "每周可投入时间调整为"),
    "learning_pace_preference": ("学习节奏改成", "学习节奏调整为"),
    "constraints": ("当前限制改成", "当前限制调整为"),
}
SYSTEM_GENERATED_KNOWLEDGE_FOUNDATION_PATTERN = re.compile(
    r"^已具备(?P<major>.+?)基础，(?P<suffix>(?:.+方向可从入门到基础逐步补全|AI 基础由系统补全为入门到基础))$"
)


def _is_complete_profile(profile: dict | None) -> bool:
    if not isinstance(profile, dict):
        return False
    if profile.get("type") != "basic_profile":
        return False
    confirmed_info = profile.get("confirmed_info")
    if not isinstance(confirmed_info, dict):
        return False
    return REQUIRED_CONFIRMED_INFO_KEYS.issubset(confirmed_info.keys()) and is_supported_current_grade(
        confirmed_info.get("current_grade")
    )


def is_complete_profile_data(profile: dict | None) -> bool:
    return _is_complete_profile(profile)


def _allows_default_fill(text: str) -> bool:
    return any(command in text for command in DEFAULT_PROFILE_COMMANDS)


def _message_content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _build_profile_input(state: OrchestrationState, conversation_summary: str) -> str:
    messages = state.get("messages", [])
    recent_contents = [
        _message_content_text(getattr(message, "content", ""))
        for message in messages[-8:]
    ]
    query = state.get("query", "")
    allow_default_fill = _allows_default_fill(query) or _allows_default_fill(conversation_summary)

    parts = [
        "请根据以下信息生成画像，并输出 SessionMessage JSON。",
        "主 Agent 对话总结：",
        conversation_summary,
        "最近对话内容：",
        "\n".join(content for content in recent_contents if content),
    ]
    if allow_default_fill:
        parts.append("允许系统补全所有缺失字段。")
    parts.append("输出 SessionMessage JSON。")
    return "\n\n".join(part for part in parts if part)


def _recent_human_texts(state: OrchestrationState) -> list[str]:
    messages = state.get("messages", [])
    texts: list[str] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            text = _message_content_text(message.content).strip()
            if text:
                texts.append(text)
    query = str(state.get("query", "")).strip()
    if query and (not texts or texts[-1] != query):
        texts.append(query)
    return texts


def _normalize_segments(texts: list[str]) -> list[str]:
    segments: list[str] = []
    for text in texts:
        for part in SPLIT_PATTERN.split(text):
            normalized = part.strip()
            if normalized:
                segments.append(normalized)
    return segments


def _clean_topic_value(value: str) -> str:
    return value.strip("：:，,。！？!?；; “”-_")


def _topic_from_segment(segment: str) -> str:
    vibecoding_match = re.search(r"vibecoding", segment, re.IGNORECASE)
    if vibecoding_match:
        return vibecoding_match.group(0)

    for prefix in TOPIC_PREFIXES:
        if not segment.startswith(prefix):
            continue
        value = _clean_topic_value(segment[len(prefix):])
        if value and value not in TOPIC_BLOCKED_VALUES:
            return value

    lowered = segment.lower()
    if lowered == "ai" or "ai应用" in lowered or "ai 应用" in lowered:
        return DEFAULT_TOPIC
    if "前端" in segment:
        return "前端开发"
    if "后端" in segment:
        return "后端开发"
    return ""


def _extract_topic(texts: list[str], segments: list[str]) -> str:
    for segment in reversed(segments):
        topic = _topic_from_segment(segment)
        if topic:
            return topic

    lowered_texts = [text.lower() for text in reversed(texts)]
    if any("ai" in text for text in lowered_texts):
        return DEFAULT_TOPIC
    if any("前端" in text for text in texts):
        return "前端开发"
    if any("后端" in text for text in texts):
        return "后端开发"
    return ""


def _topic_from_existing_profile(existing_profile: dict | None, existing_confirmed: dict) -> str:
    content_preference = existing_confirmed.get("content_preference")
    content_text = (
        " ".join(str(item) for item in content_preference if str(item).strip())
        if isinstance(content_preference, list)
        else ""
    )
    text_candidates = [
        str(existing_confirmed.get("short_term_goal", "")),
        str(existing_confirmed.get("long_term_goal", "")),
        content_text,
    ]
    if isinstance(existing_profile, dict):
        text_candidates.extend([
            str(existing_profile.get("summary_text", "")),
            str(existing_profile.get("text", "")),
        ])

    combined = "\n".join(text_candidates).lower()
    if "vibecoding" in combined:
        return "vibecoding"
    if "ai" in combined:
        return DEFAULT_TOPIC
    if "前端" in combined:
        return "前端开发"
    if "后端" in combined:
        return "后端开发"
    return ""


def _looks_like_major(segment: str) -> bool:
    if not segment or any(term in segment for term in MAJOR_BLOCKED_TERMS):
        return False
    if any(marker in segment for marker in ("改成", "调整为")):
        return False
    if any(mark in segment for mark in ("？", "?", "！", "!", "。", ".")):
        return False
    return True


def _learning_method_from_segment(segment: str) -> str:
    for marker in LEARNING_METHOD_SEGMENTS:
        if marker in segment:
            return marker if marker.startswith("喜欢") else segment
    return ""


def _goal_from_segment(segment: str) -> str:
    for marker in GOAL_SEGMENTS:
        if marker in segment:
            return marker
    return ""


def _clean_major_value(segment: str) -> str:
    value = segment.strip()
    if value.endswith("专业"):
        value = value[:-2]
    return _clean_explicit_field_value(value)


def _major_from_segment(segment: str) -> str:
    value = _clean_major_value(segment)
    if not value:
        return ""
    if len(value) > 16:
        return ""
    if (
        _topic_from_segment(segment)
        or _learning_method_from_segment(segment)
        or _goal_from_segment(segment)
        or segment in PACE_SEGMENTS
        or segment in GREETING_SEGMENTS
        or GRADE_PATTERN.search(segment)
        or "学习" in value.lower()
        or "生成" in value
    ):
        return ""
    return value if _looks_like_major(value) else ""


def _major_from_segments(segments: list[str]) -> str:
    for segment in reversed(segments):
        major = _major_from_segment(segment)
        if major:
            return major
    return ""


def _short_term_goal_from_parts(detected_goal: str, topic: str) -> str:
    if detected_goal and topic:
        return f"{detected_goal}，学习{topic}"
    if detected_goal:
        return detected_goal
    if topic:
        return f"学习{topic}"
    return ""


def _clean_explicit_field_value(value: str) -> str:
    return value.strip("：:，,。！？!?；; ")


def _extract_explicit_profile_updates(texts: list[str]) -> dict[str, object]:
    updates: dict[str, object] = {}
    for text in reversed(texts):
        normalized = text.strip()
        if not normalized:
            continue
        explicit_clauses = [
            clause.strip()
            for clause in EXPLICIT_FIELD_SPLIT_PATTERN.split(normalized)
            if clause.strip()
        ]
        for clause in explicit_clauses:
            for field_name, prefixes in EXPLICIT_PROFILE_FIELD_PREFIXES.items():
                if field_name in updates:
                    continue
                for prefix in prefixes:
                    if not clause.startswith(prefix):
                        continue
                    value = _clean_explicit_field_value(clause[len(prefix):])
                    if value:
                        updates[field_name] = value
                    break
    return updates


def _extract_profile_updates(state: OrchestrationState, *, include_defaults: bool = True) -> dict[str, object]:
    texts = _recent_human_texts(state)
    segments = _normalize_segments(texts)
    updates = _extract_explicit_profile_updates(texts)
    topic = _extract_topic(texts, segments)
    detected_goal = ""

    for segment in reversed(segments):
        grade_match = GRADE_PATTERN.search(segment)
        if "current_grade" not in updates and grade_match:
            updates["current_grade"] = grade_match.group(1)
            continue

        if "constraints" not in updates and segment in PACE_SEGMENTS:
            updates["constraints"] = segment
            updates.setdefault("experience", segment)
            continue

        if "learning_method_preference" not in updates:
            learning_method = _learning_method_from_segment(segment)
            if learning_method:
                updates["learning_method_preference"] = learning_method
                continue

        if not detected_goal:
            detected_goal = _goal_from_segment(segment)

    if "major" not in updates:
        major = _major_from_segments(segments)
        if major:
            updates["major"] = major

    if "short_term_goal" not in updates:
        short_term_goal = _short_term_goal_from_parts(detected_goal, topic)
        if short_term_goal:
            updates["short_term_goal"] = short_term_goal

    if include_defaults and not topic:
        topic = DEFAULT_TOPIC
    if include_defaults:
        updates.setdefault("major", DEFAULT_MAJOR)
    if topic:
        updates["topic"] = topic
    return updates


def _empty_confirmed_info() -> dict[str, object]:
    return {
        "current_grade": "",
        "major": "",
        "learning_stage": "",
        "has_clear_goal": "",
        "learning_method_preference": "",
        "learning_pace_preference": "",
        "content_preference": [],
        "need_guidance": "",
        "knowledge_foundation": "",
        "strengths": "",
        "weaknesses": "",
        "experience": "",
        "short_term_goal": "",
        "long_term_goal": "",
        "weekly_available_time": "",
        "constraints": "",
    }


def _unsupported_grade_question(current_grade: object) -> str:
    return (
        f"{unsupported_current_grade_error(current_grade)}"
        " 如果你想继续生成学习路径，请先告诉我对应的本科年级（大一到大四）。"
    )


def _collecting_profile_for_unsupported_grade(confirmed_info: dict[str, object]) -> dict:
    merged = _empty_confirmed_info()
    for key in merged:
        value = confirmed_info.get(key)
        if key == "content_preference":
            merged[key] = value if isinstance(value, list) else []
        elif isinstance(value, str):
            merged[key] = value

    question = _unsupported_grade_question(merged.get("current_grade"))
    return {
        "type": "collecting",
        "stage": "basic_info",
        "question_mode": "question_md",
        "confirmed_info": merged,
        "defaulted_fields": [],
        "question_md": question,
        "question_box": {"question": "", "options": []},
        "text": question,
    }


def _build_collecting_profile(state: OrchestrationState) -> dict:
    existing_profile = state.get("profile")
    existing_confirmed = (
        existing_profile.get("confirmed_info", {})
        if isinstance(existing_profile, dict) and isinstance(existing_profile.get("confirmed_info"), dict)
        else {}
    )
    updates = _extract_profile_updates(state, include_defaults=False)
    merged = _empty_confirmed_info()

    for key in merged:
        if key in existing_confirmed and existing_confirmed.get(key):
            merged[key] = existing_confirmed[key]
        elif key in updates and updates.get(key):
            merged[key] = updates[key]

    current_grade = merged.get("current_grade")
    if isinstance(current_grade, str) and current_grade.strip() and not is_supported_current_grade(current_grade):
        return _collecting_profile_for_unsupported_grade(merged)

    missing_fields = [
        field_name
        for field_name in ("current_grade", "major")
        if not isinstance(merged.get(field_name), str) or not str(merged.get(field_name)).strip()
    ]

    if missing_fields == ["current_grade", "major"]:
        question = (
            "为了生成基础画像，请先告诉我你的年级和专业。"
            "如果你愿意，也可以一起告诉我想学的方向、近期目标和每周可投入时间。"
        )
    elif missing_fields == ["current_grade"]:
        question = "为了生成基础画像，请先告诉我你的年级。"
    elif missing_fields == ["major"]:
        question = "为了生成基础画像，请先告诉我你的专业。"
    else:
        question = (
            "我还需要再确认一点信息。"
            "你可以继续补充学习方向、近期目标、每周可投入时间或当前限制。"
        )

    return {
        "type": "collecting",
        "stage": "basic_info",
        "question_mode": "question_md",
        "confirmed_info": merged,
        "defaulted_fields": [],
        "question_md": question,
        "question_box": {"question": "", "options": []},
        "text": question,
    }


def _has_minimum_profile_fields(state: OrchestrationState) -> bool:
    existing_profile = state.get("profile")
    existing_confirmed = (
        existing_profile.get("confirmed_info", {})
        if isinstance(existing_profile, dict) and isinstance(existing_profile.get("confirmed_info"), dict)
        else {}
    )
    updates = _extract_profile_updates(state, include_defaults=False)
    current_grade = existing_confirmed.get("current_grade") or updates.get("current_grade")
    major = existing_confirmed.get("major") or updates.get("major")
    return (
        isinstance(current_grade, str)
        and current_grade.strip() != ""
        and isinstance(major, str)
        and major.strip() != ""
    )


def _can_complete_collecting_profile_locally(state: OrchestrationState) -> bool:
    profile = state.get("profile")
    if not isinstance(profile, dict) or profile.get("type") != "collecting":
        return False
    return _has_minimum_profile_fields(state)


def _profile_question_box() -> dict[str, object]:
    return {
        "question": "画像已生成，下一步要继续生成学习路径吗？",
        "options": [
            {
                "label": "继续生成学习路径",
                "value": "继续生成学习路径",
                "description": "根据当前画像生成今天可执行的课程路径",
                "target_fields": [],
                "fills": {},
            },
            {
                "label": "修改画像方向",
                "value": "修改画像方向",
                "description": "继续补充年级、专业、目标或偏好",
                "target_fields": [],
                "fills": {},
            },
        ],
    }


def _persist_profile(user_id: str, profile_dict: dict) -> None:
    from sqlmodel import Session

    from app.database import get_engine
    from app.services.course_knowledge_service import delete_user_course_outlines
    from app.services.profile_service import upsert_user_profile

    try:
        with Session(get_engine()) as db_session:
            upsert_user_profile(db_session, user_id, profile_dict)
            # Any profile rewrite can invalidate saved outlines because chapter pacing
            # and learning checkpoints are derived from the latest profile assumptions.
            if profile_dict.get("type") in {"basic_profile", "collecting"}:
                delete_user_course_outlines(db_session, user_id)
        logger.info("Profile persisted for user %s", user_id)
    except Exception as exc:
        logger.error("Failed to persist profile for user %s: %s", user_id, exc)


def _resolved_profile_text(
    existing_confirmed: dict,
    updates: dict[str, object],
    key: str,
    *,
    allow_default_fill: bool,
    default_value: str = "",
) -> str:
    value = updates.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    existing_value = existing_confirmed.get(key)
    if isinstance(existing_value, str) and existing_value.strip():
        return existing_value.strip()
    return default_value if allow_default_fill else ""


def _resolved_content_preference(
    existing_confirmed: dict,
    *,
    topic: str,
    allow_default_fill: bool,
) -> list[object]:
    existing_content_preference = existing_confirmed.get("content_preference")
    if isinstance(existing_content_preference, list) and existing_content_preference:
        return existing_content_preference
    if topic:
        return [topic]
    if allow_default_fill:
        return ["代码实践", "项目案例", "AI 对话调试"]
    return []


def _apply_profile_update_overrides(confirmed: dict[str, object], updates: dict[str, object]) -> None:
    for key in (
        "current_grade",
        "major",
        "experience",
        "constraints",
        "short_term_goal",
        "long_term_goal",
        "weekly_available_time",
        "learning_pace_preference",
    ):
        if key in updates:
            confirmed[key] = updates[key]


def _rewrite_system_generated_knowledge_foundation(
    existing_value: object,
    major: object,
) -> str:
    existing_text = str(existing_value or "").strip()
    major_text = str(major or "").strip()
    if not existing_text or not major_text:
        return ""
    match = SYSTEM_GENERATED_KNOWLEDGE_FOUNDATION_PATTERN.fullmatch(existing_text)
    if match is None:
        return ""
    return f"已具备{major_text}基础，{match.group('suffix')}"


def _generated_knowledge_foundation(major: object, topic: str) -> str:
    major_text = str(major or "").strip()
    topic_text = str(topic or "").strip()
    if not major_text or not topic_text:
        return ""
    return f"已具备{major_text}基础，{topic_text}方向可从入门到基础逐步补全"


def _defaulted_profile_fields(
    confirmed: dict[str, object],
    updates: dict[str, object],
    existing_confirmed: dict,
    *,
    allow_default_fill: bool,
) -> list[str]:
    if not allow_default_fill:
        return []
    return [
        key
        for key, _value in confirmed.items()
        if key not in updates and (
            not isinstance(existing_confirmed, dict)
            or key not in existing_confirmed
            or not existing_confirmed.get(key)
        )
    ]


def _local_profile_summary(confirmed: dict[str, object], topic: str) -> str:
    summary_parts = [f"{confirmed['current_grade']}{confirmed['major']}"]
    if confirmed["short_term_goal"]:
        summary_parts.append(f"目标是{confirmed['short_term_goal']}")
    if topic and topic not in str(confirmed["short_term_goal"]):
        summary_parts.append(f"想学习{topic}")
    if confirmed["learning_method_preference"]:
        summary_parts.append(f"偏好{confirmed['learning_method_preference']}")
    return f"【基础学习画像总结】{'，'.join(str(part) for part in summary_parts if str(part).strip())}。"


def _build_local_confirmed_info(
    existing_confirmed: dict,
    updates: dict[str, object],
    *,
    topic: str,
    allow_default_fill: bool,
    has_existing_complete_profile: bool,
) -> dict[str, object]:
    def resolved(key: str, default_value: str = "") -> str:
        return _resolved_profile_text(
            existing_confirmed,
            updates,
            key,
            allow_default_fill=allow_default_fill,
            default_value=default_value,
        )

    confirmed: dict[str, object] = {
        "current_grade": resolved("current_grade", DEFAULT_GRADE if allow_default_fill else UNKNOWN_VALUE),
        "major": resolved("major", DEFAULT_MAJOR),
        "learning_stage": resolved("learning_stage", "有基础"),
        "has_clear_goal": resolved("has_clear_goal", "大致有方向"),
        "learning_method_preference": resolved("learning_method_preference", "项目驱动学习"),
        "learning_pace_preference": resolved("learning_pace_preference", "按项目里程碑推进"),
        "content_preference": _resolved_content_preference(existing_confirmed, topic=topic, allow_default_fill=allow_default_fill),
        "need_guidance": resolved("need_guidance", "需要轻量提醒"),
        "knowledge_foundation": resolved("knowledge_foundation"),
        "strengths": resolved("strengths", "工程实现与课程学习能力"),
        "weaknesses": resolved("weaknesses", "大型项目实战经验、数据库设计能力、英文阅读速度"),
        "experience": resolved("experience", "平时学习"),
        "short_term_goal": resolved("short_term_goal", f"围绕{topic or DEFAULT_TOPIC}完成一个可运行的课程级项目"),
        "long_term_goal": resolved("long_term_goal", f"形成{topic or DEFAULT_TOPIC}方向的应用开发能力"),
        "weekly_available_time": resolved("weekly_available_time", "每周 6-10 小时"),
        "constraints": resolved("constraints", "平时学习节奏，避免过高强度"),
    }
    _apply_profile_update_overrides(confirmed, updates)
    if "knowledge_foundation" not in updates:
        rewritten_knowledge_foundation = _rewrite_system_generated_knowledge_foundation(
            existing_confirmed.get("knowledge_foundation"),
            confirmed.get("major"),
        )
        if rewritten_knowledge_foundation:
            confirmed["knowledge_foundation"] = rewritten_knowledge_foundation
    if not confirmed["knowledge_foundation"] and (allow_default_fill or has_existing_complete_profile):
        confirmed["knowledge_foundation"] = _generated_knowledge_foundation(
            confirmed.get("major"),
            topic,
        )
    return confirmed


def _build_local_profile(state: OrchestrationState, *, allow_default_fill: bool) -> dict:
    existing_profile = state.get("profile")
    has_existing_complete_profile = _is_complete_profile(existing_profile)
    existing_confirmed = (
        existing_profile.get("confirmed_info", {})
        if isinstance(existing_profile, dict) and isinstance(existing_profile.get("confirmed_info"), dict)
        else {}
    )
    updates = _extract_profile_updates(state, include_defaults=allow_default_fill)
    topic = str(updates.pop("topic", DEFAULT_TOPIC if allow_default_fill else "")).strip()
    if not topic:
        topic = _topic_from_existing_profile(existing_profile, existing_confirmed)

    confirmed = _build_local_confirmed_info(
        existing_confirmed,
        updates,
        topic=topic,
        allow_default_fill=allow_default_fill,
        has_existing_complete_profile=has_existing_complete_profile,
    )
    if not is_supported_current_grade(confirmed.get("current_grade")):
        return _collecting_profile_for_unsupported_grade(confirmed)
    defaulted_fields = _defaulted_profile_fields(
        confirmed,
        updates,
        existing_confirmed,
        allow_default_fill=allow_default_fill,
    )
    summary = _local_profile_summary(confirmed, topic)

    return {
        "type": "basic_profile",
        "stage": "generated",
        "question_mode": "question_box",
        "confirmed_info": confirmed,
        "defaulted_fields": defaulted_fields,
        "question_md": "画像已生成，是否继续生成学习路径？",
        "question_box": _profile_question_box(),
        "text": summary,
        "summary_text": summary,
    }


def _should_use_local_profile(state: OrchestrationState) -> bool:
    query = str(state.get("query", "")).strip()
    if _allows_default_fill(query):
        return True
    if not query:
        return False
    separators = any(mark in query for mark in ("，", ",", "、", ";", "；"))
    has_profile_signal = (
        bool(GRADE_PATTERN.search(query))
        or "专业" in query
        or "平时学习" in query
        or "ai" in query.lower()
        or "vibecoding" in query.lower()
    )
    has_existing_profile = _is_complete_profile(state.get("profile"))
    if has_existing_profile:
        return separators or has_profile_signal
    return has_profile_signal


async def run_profile_agent(state: OrchestrationState, llm: BaseChatModel) -> dict:
    """One-shot profile generation: receives conversation summary, outputs structured profile."""
    tool_args = extract_last_tool_call_args(state)
    conversation_summary = tool_args.get("conversation_summary", state["query"])
    profile_input = _build_profile_input(state, conversation_summary)
    allow_default_fill = _allows_default_fill(str(state.get("query", "")))

    if not allow_default_fill and not _is_complete_profile(state.get("profile")) and not _has_minimum_profile_fields(state):
        profile_dict = _build_collecting_profile(state)
        _persist_profile(state["user_id"], profile_dict)
        return {"profile": profile_dict, "response": profile_dict.get("text", "")}

    if _can_complete_collecting_profile_locally(state) or _should_use_local_profile(state):
        profile_dict = _build_local_profile(state, allow_default_fill=allow_default_fill)
        _persist_profile(state["user_id"], profile_dict)
        return {"profile": profile_dict, "response": profile_dict.get("text", "")}

    structured_llm = llm.with_structured_output(ProfileOutput)
    prompt = ChatPromptTemplate.from_messages([
        ("system", PROFILE_AGENT_SYSTEM_PROMPT),
        ("human", "{profile_input}"),
    ])
    chain = prompt | structured_llm

    try:
        result: ProfileOutput = await chain.ainvoke({"profile_input": profile_input})
    except Exception as exc:
        logger.warning("ProfileAgent structured output failed: %s", exc)
        if allow_default_fill or _is_complete_profile(state.get("profile")):
            profile_dict = _build_local_profile(state, allow_default_fill=allow_default_fill)
            _persist_profile(state["user_id"], profile_dict)
            return {"profile": profile_dict, "response": profile_dict.get("text", "")}
        return {"error": f"画像生成失败：{str(exc)[:200]}"}

    profile_dict = result.model_dump()
    confirmed_info = profile_dict.get("confirmed_info", {})
    if isinstance(confirmed_info, dict) and not is_supported_current_grade(confirmed_info.get("current_grade")):
        profile_dict = _collecting_profile_for_unsupported_grade(confirmed_info)
    _persist_profile(state["user_id"], profile_dict)

    return {"profile": profile_dict, "response": profile_dict.get("text", "")}


def create_profile_agent_node(llm: BaseChatModel):
    async def profile_agent_node(state: OrchestrationState) -> dict:
        agent_result = await run_profile_agent(state, llm)

        tool_call_id = extract_last_tool_call_id(state)
        tool_message = ToolMessage(
            content=json.dumps(agent_result, ensure_ascii=False),
            tool_call_id=tool_call_id or "unknown",
        )

        result = {"messages": [tool_message]}
        if agent_result.get("profile") is not None:
            result["profile"] = agent_result["profile"]
            result["course_knowledge"] = None
        if agent_result.get("response") is not None:
            result["response"] = agent_result["response"]
        elif agent_result.get("error") is not None:
            result["response"] = agent_result["error"]
        return result

    return profile_agent_node
