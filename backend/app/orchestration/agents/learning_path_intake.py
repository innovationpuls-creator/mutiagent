from __future__ import annotations

import asyncio
import copy
import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.database import get_engine
from app.orchestration.agents.models import (
    LearningPathIntakeDraftOutput,
    LearningPathIntakeOutput,
)
from app.orchestration.agents.profile import is_complete_profile_data
from app.orchestration.agents.prompts import LEARNING_PATH_INTAKE_AGENT_SYSTEM_PROMPT
from app.orchestration.agents.utils import extract_last_tool_call_id
from app.orchestration.grade_contract import grade_year_from_current_grade
from app.orchestration.state import OrchestrationState
from app.services.conversation_session_service import (
    load_or_create_session,
    replace_latest_learning_path_intake,
)

logger = logging.getLogger(__name__)

LEARNING_PATH_INTAKE_STRUCTURED_TIMEOUT_SECONDS = 90.0
LEARNING_PATH_INTAKE_RETRY_ERROR = "课程草案生成失败，请重试生成学习路径草案。"

CONFIRMATION_MARKERS = (
    "可以",
    "确认",
    "没问题",
    "就按这个",
    "按这个来",
    "听你的",
    "可以开始",
    "开始吧",
    "好的",
    "行",
    "继续",
)
CANCELLATION_MARKERS = (
    "不要了",
    "算了",
    "先不改",
)
MODIFICATION_MARKERS = (
    "换成",
    "改成",
    "调整",
    "修改",
    "不想学",
    "不学",
    "我想学",
    "想学",
    "换一门",
    "换个",
)
TOPIC_MARKERS = (
    ("数据结构", "数据结构"),
    ("算法", "算法"),
    ("前端", "前端开发"),
    ("后端", "后端开发"),
)


def is_intake_modification_query(text: str) -> bool:
    normalized = text.strip()
    if "确认修改" in normalized or "确认调整" in normalized:
        return False
    return bool(normalized) and any(
        marker in normalized for marker in MODIFICATION_MARKERS
    )


def is_intake_confirmation_query(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if "确认修改" in normalized or "确认调整" in normalized:
        return True
    if is_intake_modification_query(normalized):
        return False
    return any(marker in normalized for marker in CONFIRMATION_MARKERS)


def is_intake_cancellation_query(text: str) -> bool:
    normalized = text.strip()
    return bool(normalized) and any(
        marker in normalized for marker in CANCELLATION_MARKERS
    )


def latest_intake_from_state(state: OrchestrationState | dict) -> dict | None:
    intake = state.get("learning_path_intake")
    if isinstance(intake, dict) and intake.get("type") == "learning_path_intake":
        return intake

    messages = state.get("messages", [])
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        parsed = _intake_from_message(message)
        if parsed is not None:
            return parsed
    return None


async def run_learning_path_intake_agent(
    state: OrchestrationState, llm: BaseChatModel
) -> dict:
    query = str(state.get("query", "")).strip()
    existing_intake = latest_intake_from_state(state)

    if (
        existing_intake is not None
        and existing_intake.get("status") == "risk_pending"
        and is_intake_cancellation_query(query)
    ):
        rolled_back = copy.deepcopy(existing_intake)
        rolled_back["status"] = "draft"
        rolled_back["requires_second_confirmation"] = False
        rolled_back["risk_warnings"] = []
        _persist_learning_path_intake(state, rolled_back)
        return {
            "learning_path_intake": rolled_back,
            "response": _risk_cancelled_response_text(rolled_back),
        }

    if existing_intake is not None and is_intake_confirmation_query(query):
        confirmed = copy.deepcopy(existing_intake)
        confirmed["status"] = "confirmed"
        confirmed["requires_second_confirmation"] = False
        confirmed["risk_warnings"] = []
        _persist_learning_path_intake(state, confirmed)
        return {
            "learning_path_intake": confirmed,
            "response": _confirmed_response_text(confirmed),
        }

    profile = state.get("profile")
    if not is_complete_profile_data(profile):
        return {"error": "请先完成基础画像再生成学习路径。", "hard_error": True}

    try:
        intake = await _invoke_intake_draft(
            state, llm, query=query, profile=profile, existing_intake=existing_intake
        )
    except Exception as exc:
        logger.warning(
            "LearningPathIntakeAgent structured output failed: %s: %s",
            type(exc).__name__,
            exc,
        )
        return {
            "error": f"{LEARNING_PATH_INTAKE_RETRY_ERROR} ({type(exc).__name__}: {exc})",
            "hard_error": True,
        }

    _check_risk_pending(state, intake)
    _persist_learning_path_intake(state, intake)
    return {
        "learning_path_intake": intake,
        "response": _draft_response_text(intake),
    }


def create_learning_path_intake_agent_node(llm: BaseChatModel):
    async def learning_path_intake_agent_node(state: OrchestrationState) -> dict:
        agent_result = await run_learning_path_intake_agent(state, llm)

        tool_call_id = extract_last_tool_call_id(state)
        tool_message = ToolMessage(
            content=json.dumps(agent_result, ensure_ascii=False),
            tool_call_id=tool_call_id or "unknown",
        )

        result = {"messages": [tool_message]}
        if agent_result.get("learning_path_intake") is not None:
            result["learning_path_intake"] = agent_result["learning_path_intake"]
            result["response"] = agent_result.get("response", "")
        if agent_result.get("error") is not None:
            result["response"] = agent_result["error"]
        return result

    return learning_path_intake_agent_node


def _intake_from_message(message: object) -> dict | None:
    if isinstance(message, dict) and message.get("type") == "learning_path_intake":
        return message
    if not isinstance(message, BaseMessage):
        return None
    content = message.content
    if not isinstance(content, str):
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        intake = parsed.get("learning_path_intake", parsed)
        if isinstance(intake, dict) and intake.get("type") == "learning_path_intake":
            return intake
    return None


async def _invoke_intake_draft(
    state: OrchestrationState | dict,
    llm: BaseChatModel,
    *,
    query: str,
    profile: dict,
    existing_intake: dict | None,
) -> dict:
    if not hasattr(llm, "with_structured_output"):
        logger.warning(
            "LearningPathIntakeAgent LLM lacks structured output; using local draft fallback."
        )
        return _build_intake_draft(
            profile,
            query=query,
            user_modification_summary=query
            if is_intake_modification_query(query)
            else "",
        )

    structured_llm = llm.with_structured_output(LearningPathIntakeDraftOutput)
    messages = [
        SystemMessage(content=LEARNING_PATH_INTAKE_AGENT_SYSTEM_PROMPT),
        HumanMessage(
            content=_build_intake_generation_input(
                state, query, profile, existing_intake
            )
        ),
    ]
    if hasattr(structured_llm, "ainvoke"):
        invoke_result = structured_llm.ainvoke(messages)
    elif callable(structured_llm):
        invoke_result = structured_llm(messages)
    else:
        logger.warning(
            "LearningPathIntakeAgent structured output is not invokable; using local draft fallback."
        )
        return _build_intake_draft(
            profile,
            query=query,
            user_modification_summary=query
            if is_intake_modification_query(query)
            else "",
        )

    result = await asyncio.wait_for(
        invoke_result,
        timeout=LEARNING_PATH_INTAKE_STRUCTURED_TIMEOUT_SECONDS,
    )
    intake = _normalize_intake_draft(
        _raw_intake_to_dict(result), profile=profile, query=query
    )
    return LearningPathIntakeOutput.model_validate(intake).model_dump()


def _raw_intake_to_dict(result: object) -> dict:
    if isinstance(result, LearningPathIntakeOutput | LearningPathIntakeDraftOutput):
        return result.model_dump()
    if hasattr(result, "model_dump"):
        dumped = result.model_dump()
        if isinstance(dumped, dict):
            return dumped
    if isinstance(result, dict):
        return copy.deepcopy(result)
    return LearningPathIntakeOutput.model_validate(result).model_dump()


def _build_intake_generation_input(
    state: OrchestrationState | dict,
    query: str,
    profile: dict,
    existing_intake: dict | None,
) -> str:
    confirmed = profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    return "\n".join(
        [
            "请根据以下上下文生成课程草案 JSON。",
            f"用户最新输入：{query}",
            f"已完成画像：{json.dumps(confirmed, ensure_ascii=False)}",
            f"画像摘要：{profile.get('summary_text') or profile.get('text') or ''}",
            f"已有课程草案：{json.dumps(existing_intake or {}, ensure_ascii=False)}",
            f"已有学习路径：{json.dumps(state.get('year_learning_paths') or {}, ensure_ascii=False)}",
            "生成规则：",
            "- 课程数量必须由你根据画像和目标判断，但只能在 4-10 门之间。",
            "- 课程必须与用户目标、年级、基础、偏好和每周时间匹配。",
            "- 如果用户自然表达了修改方向，要吸收修改并输出新的 draft。",
            "- 不要输出 confirmed；用户确认由系统单独处理。",
            "- 不要输出自然语言解释，只输出结构化对象。",
        ]
    )


def _normalize_intake_draft(intake: dict, *, profile: dict, query: str) -> dict:
    confirmed = profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    grade_name = str(confirmed.get("current_grade", "")).strip()
    grade_year = grade_year_from_current_grade(grade_name)
    intake["type"] = "learning_path_intake"
    intake["status"] = "draft"
    if grade_name:
        intake["grade_name"] = grade_name
    if grade_year:
        intake["grade_year"] = grade_year
    if (
        is_intake_modification_query(query)
        and not str(intake.get("user_modification_summary", "")).strip()
    ):
        intake["user_modification_summary"] = query
    intake["requires_second_confirmation"] = False
    intake["risk_warnings"] = []
    return intake


def _build_intake_draft(
    profile: dict, *, query: str, user_modification_summary: str
) -> dict:
    confirmed = profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    current_grade = (
        confirmed.get("current_grade", "") if isinstance(confirmed, dict) else ""
    )
    grade_name = str(current_grade).strip()
    grade_year = grade_year_from_current_grade(grade_name)
    learning_topic = _learning_topic_from_texts(query, profile, confirmed)
    courses = _courses_for_topic(learning_topic)
    return {
        "type": "learning_path_intake",
        "status": "draft",
        "grade_year": grade_year,
        "grade_name": grade_name,
        "learning_topic": learning_topic,
        "courses": courses,
        "recommendation_reasons": _recommendation_reasons(confirmed, learning_topic),
        "user_modification_summary": user_modification_summary,
        "risk_warnings": [],
        "requires_second_confirmation": False,
    }


def _learning_topic_from_texts(query: str, profile: dict, confirmed: dict) -> str:
    texts = [
        query,
        str(confirmed.get("short_term_goal", "")),
        str(confirmed.get("long_term_goal", "")),
        str(profile.get("summary_text", "")) if isinstance(profile, dict) else "",
        str(profile.get("text", "")) if isinstance(profile, dict) else "",
    ]
    combined = "\n".join(text for text in texts if text)
    for marker, topic in TOPIC_MARKERS:
        if marker in combined:
            return topic
    return (
        str(confirmed.get("short_term_goal", "")).replace("学习", "", 1).strip()
        or "学习路径"
    )


def _courses_for_topic(learning_topic: str) -> list[dict[str, str]]:
    if learning_topic == "数据结构":
        return [
            {
                "title": "数据结构入门与复杂度基础",
                "purpose": "建立抽象数据类型、复杂度和基本分析能力",
            },
            {
                "title": "线性结构实践",
                "purpose": "掌握数组、链表、栈、队列的实现与使用场景",
            },
            {
                "title": "树与递归基础",
                "purpose": "理解树结构、递归遍历和层次化问题拆解",
            },
            {
                "title": "查找、排序与哈希",
                "purpose": "建立常见查找排序策略和哈希表应用能力",
            },
            {
                "title": "图结构与综合项目",
                "purpose": "完成图遍历、路径问题和综合数据结构应用",
            },
        ]
    if learning_topic == "算法":
        return [
            {"title": "算法复杂度与问题建模", "purpose": "建立算法分析和输入规模意识"},
            {"title": "基础排序与查找算法", "purpose": "掌握常见排序、二分和哈希查找"},
            {"title": "递归、分治与回溯", "purpose": "训练结构化拆解复杂问题"},
            {"title": "动态规划入门", "purpose": "掌握状态定义、转移和边界处理"},
        ]
    return [
        {"title": f"{learning_topic}入门基础", "purpose": "建立方向认知和基础概念"},
        {
            "title": f"{learning_topic}核心能力训练",
            "purpose": "围绕核心技能进行系统练习",
        },
        {"title": f"{learning_topic}实践任务", "purpose": "通过小项目形成可验证产出"},
        {"title": f"{learning_topic}综合复盘", "purpose": "总结学习成果并明确下一步"},
    ]


def _recommendation_reasons(confirmed: dict, learning_topic: str) -> list[str]:
    reasons = [f"近期目标指向{learning_topic}"]
    current_grade = str(confirmed.get("current_grade", "")).strip()
    if current_grade:
        reasons.append(f"当前年级是{current_grade}，适合先形成可持续的课程顺序")
    learning_stage = str(confirmed.get("learning_stage", "")).strip()
    if learning_stage:
        reasons.append(f"当前阶段是{learning_stage}，先从基础和实践闭环开始")
    pace = str(confirmed.get("learning_pace_preference", "")).strip()
    if pace:
        reasons.append(f"学习节奏偏好为{pace}，课程数量保持适中")
    return reasons[:4]


def _draft_response_text(intake: dict) -> str:
    courses = intake.get("courses", [])
    course_lines = [
        f"{index}. {course.get('title')}：{course.get('purpose')}"
        for index, course in enumerate(courses, start=1)
        if isinstance(course, dict)
    ]
    reasons = intake.get("recommendation_reasons", [])
    reason_text = "；".join(str(reason) for reason in reasons if str(reason).strip())

    lines = [
        "基础画像已经完成，我先把正式学习路径生成前的课程草稿整理出来。",
        f"推荐理由：{reason_text}。",
        f"年级：{intake.get('grade_name')}；主题：{intake.get('learning_topic')}。",
        "课程草稿：",
        *course_lines,
    ]

    if intake.get("status") == "risk_pending":
        lines.append("\n⚠️【风险提示】检测到本次修改包含以下敏感操作：")
        lines.extend(f"- {w}" for w in intake.get("risk_warnings", []))
        lines.append(
            "这会导致相关课程的已生成内容或进度丢失。下一步是确认是否继续替换或删除这些课程。确认继续修改可直接回复“确认”“可以”“好的”“行”“继续”，也可以说“先不改”保留原路径。"
        )
    else:
        lines.append(
            "下一步是生成正式学习路径，系统会把这份草稿变成具体课程顺序、学习目标、时间安排和下一步行动。可以开始下一步吗？如果同意，可以直接回复“确认”“可以”“继续”，也可以点击“确认并生成学习路径”。如果想改，直接说“把第2门换成算法实战”“删掉第3门”或“主题改成前端”。"
        )

    return "\n".join(lines)


def _check_risk_pending(state: OrchestrationState | dict, intake: dict) -> None:
    profile = state.get("profile")
    confirmed = profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    user_id = state.get("user_id", "")
    if not user_id:
        return

    protected = {}
    from sqlmodel import Session, select

    from app.database import get_engine
    from app.models import UserCourseKnowledgeOutline

    try:
        with Session(get_engine()) as db_session:
            outlines = db_session.exec(
                select(UserCourseKnowledgeOutline).where(
                    UserCourseKnowledgeOutline.user_uid == user_id
                )
            ).all()
            for o in outlines:
                if o.course_name:
                    protected[o.course_name.strip()] = "已有课程大纲"
    except Exception as exc:
        logger.warning("Failed to query course outlines for user %s: %s", user_id, exc)

    year_paths = state.get("year_learning_paths")
    if (not year_paths or not isinstance(year_paths, dict)) and user_id:
        try:
            with Session(get_engine()) as db_session:
                from app.services.learning_path_service import (
                    get_all_year_learning_paths,
                )

                year_paths = get_all_year_learning_paths(db_session, user_id)
        except Exception as exc:
            logger.warning(
                "Failed to query year learning paths for user %s: %s", user_id, exc
            )

    if isinstance(year_paths, dict):
        for grade_year, path in year_paths.items():
            if not isinstance(path, dict):
                continue
            current = path.get("current_learning_course")
            if isinstance(current, dict):
                curr_title = current.get("course_or_chapter_theme")
                curr_state = current.get("progress_state")
                if curr_title and curr_state in {"in_progress", "completed"}:
                    protected[curr_title.strip()] = "已开始学习"
            grade_plans = path.get("grade_plans", {})
            if isinstance(grade_plans, dict):
                for gp in grade_plans.values():
                    if not isinstance(gp, dict):
                        continue
                    course_nodes = gp.get("course_nodes", [])
                    if isinstance(course_nodes, list):
                        for c in course_nodes:
                            if isinstance(c, dict):
                                c_title = c.get("course_or_chapter_theme")
                                c_state = c.get("progress_state")
                                if c_title and c_state in {"in_progress", "completed"}:
                                    protected[c_title.strip()] = "已开始学习"

    new_course_titles = {
        c.get("title", "").strip()
        for c in intake.get("courses", [])
        if isinstance(c, dict)
    }
    warnings = []
    for title, reason in protected.items():
        if title not in new_course_titles:
            warnings.append(f"替换/删除{reason}的课程《{title}》")

    if warnings:
        intake["status"] = "risk_pending"
        intake["requires_second_confirmation"] = True
        intake["risk_warnings"] = warnings


def _confirmed_response_text(intake: dict) -> str:
    topic = intake.get("learning_topic", "")
    return f"好的，已确认这份{topic}学习路径草稿。下一步会生成正式学习路径，包括课程顺序、学习目标、时间安排和下一步行动。"


def _risk_cancelled_response_text(intake: dict) -> str:
    topic = intake.get("learning_topic", "")
    topic_text = f"{topic}的" if topic else ""
    return f"好的，已保留原学习路径，不做本次修改。{topic_text}课程草稿已回到普通草稿状态，你也可以继续告诉我哪里需要修改。"


def _persist_learning_path_intake(
    state: OrchestrationState | dict, intake: dict
) -> None:
    session_id = str(state.get("session_id", "")).strip()
    user_id = str(state.get("user_id", "")).strip()
    if not session_id or not user_id:
        return

    from sqlmodel import Session

    try:
        with Session(get_engine()) as db_session:
            load_or_create_session(db_session, session_id, user_id)
            replace_latest_learning_path_intake(db_session, session_id, intake)
    except Exception as exc:
        logger.warning(
            "Failed to persist learning_path_intake for session %s: %s", session_id, exc
        )
