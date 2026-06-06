"""Agent delegation rule engine.

Enforces hard rules (blocking) and provides soft hints for the supervisor LLM.
Hard rules gate which worker agents can be called based on system state.
Soft hints inject context into the supervisor's system prompt to guide LLM decisions.

Updated for one-shot profile flow and year_learning_paths schema.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from app.orchestration.agents.profile import EXPLICIT_PROFILE_FIELD_PREFIXES, is_complete_profile_data

# ── Agent keys ───────────────────────────────────────────────────────────
AGENT_PROFILE = "profile_agent"
AGENT_LEARNING_PATH = "learning_path_agent"
AGENT_COURSE_KNOWLEDGE = "course_knowledge_agent"
AGENT_SECTION_MARKDOWN = "section_markdown_agent"
AGENT_SECTION_VIDEO_SEARCH = "section_video_search_agent"
AGENT_SECTION_HTML_ANIMATION = "section_html_animation_agent"

ALL_WORKER_AGENTS = {
    AGENT_PROFILE,
    AGENT_LEARNING_PATH,
    AGENT_COURSE_KNOWLEDGE,
    AGENT_SECTION_MARKDOWN,
    AGENT_SECTION_VIDEO_SEARCH,
    AGENT_SECTION_HTML_ANIMATION,
}

# Keywords for intent detection
_NAVIGATION_QUERIES = {
    "下一步", "然后", "接下来", "继续", "好的", "ok", "好", "嗯", "哦", "好了",
}
_COURSE_START_KEYWORDS = {
    "start_first_course", "开始第一门课", "开始课程", "开始学习", "生成课程",
}
_COURSE_OUTLINE_REGENERATION_KEYWORDS = {
    "重新生成该课程的大纲",
    "重新生成该课程大纲",
    "重新生成这门课的大纲",
    "重新生成这门课大纲",
    "重新生成课程大纲",
}
_COURSE_RESOURCE_GENERATION_KEYWORDS = {
    "生成当前课程教学内容",
    "生成课程教学内容",
    "生成第一章内容",
    "生成章节内容",
    "开始学习这门课",
    "开始学习当前课程",
    "根据课程大纲生成教学内容",
}
_COURSE_CHANGE_KEYWORDS = {
    "换一门课", "生成一门新课", "新课",
}
_REVIEW_PLAN_KEYWORDS = {
    "review_plan",
    "先看看学习路径",
    "看看路径",
    "回顾规划",
    "我的学习路径里面要学哪些课",
    "学习路径里面要学哪些课",
}
_PATH_REFRESH_KEYWORDS = {
    "继续生成学习路径",
    "更新学习路径",
}
_PROFILE_UPDATE_KEYWORDS = {
    "修改画像方向",
    "更新个人画像",
}
_DEFAULT_PROFILE_COMMANDS = ("默认", "直接", "随便帮我填", "不确定的你随便帮我填", "帮我生成")
_COMPLETED_REPLAN_RESPONSE_PREFIX = "当前所有任务已经完成。"
_PROFILE_UPDATE_PROMPT_PREFIX = "可以。更新个人画像前，请先直接告诉我你想调整的具体信息。"
_GRADE_PATTERN = re.compile(r"(大[一二三四]|大[1234]|[一二三四]年级|研[一二三])")
_REQUIRED_CONFIRMED_INFO_KEYS = frozenset({
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
_LEAF_RESOURCE_BLOCK_PATTERN = re.compile(
    r"\[LEAF_RESOURCE_GENERATION\](?P<body>.*?)\[/LEAF_RESOURCE_GENERATION\]",
    re.DOTALL,
)
_LEAF_REGEN_PENDING_PATTERN = re.compile(
    r"\[LEAF_REGEN_PENDING\](?P<body>.*?)\[/LEAF_REGEN_PENDING\]",
    re.DOTALL,
)


@dataclass
class RuleResult:
    allowed_agents: set[str] = field(default_factory=lambda: set(ALL_WORKER_AGENTS))
    blocked_agents: set[str] = field(default_factory=set)
    system_hints: list[str] = field(default_factory=list)
    force_call: str | None = None
    skip_supervisor_llm: bool = False


# ── Intent helpers ───────────────────────────────────────────────────────

def is_navigation_query(query: str) -> bool:
    q = query.strip().lower()
    if not q:
        return False
    normalized = re.sub(r"[。！？!?,，、；：\s]+", "", q)
    return normalized in _NAVIGATION_QUERIES or normalized in {
        "然后呢",
        "接下来呢",
        "下一步呢",
        "下一步是什么",
        "下一步是什么呢",
        "现在我应该干嘛",
        "我应该干嘛",
        "现在该做什么",
        "接下来我该做什么",
    }

def is_course_start_query(query: str) -> bool:
    q = query.strip().lower()
    return any(kw in q for kw in _COURSE_START_KEYWORDS)


def is_course_outline_regeneration_query(query: str) -> bool:
    q = query.strip().lower()
    if not q:
        return False
    return any(keyword in q for keyword in _COURSE_OUTLINE_REGENERATION_KEYWORDS)


def is_course_resource_generation_query(query: str) -> bool:
    q = query.strip().lower()
    if not q:
        return False
    return any(keyword in q for keyword in _COURSE_RESOURCE_GENERATION_KEYWORDS)

def is_course_change_query(query: str) -> bool:
    q = query.strip().lower()
    if not q:
        return False
    has_change_signal = "不想要" in q or any(kw in q for kw in _COURSE_CHANGE_KEYWORDS)
    return has_change_signal

def is_review_plan_query(query: str) -> bool:
    q = query.strip().lower()
    return any(kw in q for kw in _REVIEW_PLAN_KEYWORDS)


def is_learning_path_refresh_query(query: str) -> bool:
    q = query.strip()
    return any(keyword in q for keyword in _PATH_REFRESH_KEYWORDS)


def is_profile_update_query(query: str) -> bool:
    q = query.strip()
    return any(keyword in q for keyword in _PROFILE_UPDATE_KEYWORDS)


def is_default_profile_query(query: str) -> bool:
    q = query.strip()
    return any(kw in q for kw in _DEFAULT_PROFILE_COMMANDS)


def _parse_key_value_block(body: str, allowed_keys: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized_key = key.strip()
        if normalized_key not in allowed_keys:
            continue
        result[normalized_key] = value.strip()
    return result


def parse_leaf_resource_generation_request(query: str) -> dict[str, str] | None:
    match = _LEAF_RESOURCE_BLOCK_PATTERN.search(query)
    if match is None:
        return None
    parsed = _parse_key_value_block(
        match.group("body"),
        {"course_node_id", "chapter_section_id", "scope", "mode"},
    )
    required = {"course_node_id", "chapter_section_id", "scope", "mode"}
    if not required.issubset(parsed.keys()):
        return None
    return parsed


def parse_leaf_regeneration_pending_marker(text: str) -> dict[str, str] | None:
    match = _LEAF_REGEN_PENDING_PATTERN.search(text)
    if match is None:
        return None
    parsed = _parse_key_value_block(
        match.group("body"),
        {"course_node_id", "chapter_section_id"},
    )
    required = {"course_node_id", "chapter_section_id"}
    if not required.issubset(parsed.keys()):
        return None
    return parsed


def _has_explicit_profile_field_update(query: str) -> bool:
    clauses = [clause.strip() for clause in re.split(r"[，,、；;]+", query) if clause.strip()]
    for clause in clauses:
        for prefixes in EXPLICIT_PROFILE_FIELD_PREFIXES.values():
            for prefix in prefixes:
                if not clause.startswith(prefix):
                    continue
                value = clause[len(prefix):].strip("：:，,。！？!?；; ")
                if value:
                    return True
    return False


def is_profile_refinement_query(query: str) -> bool:
    q = query.strip()
    if not q:
        return False
    if _has_explicit_profile_field_update(q):
        return True
    has_grade = bool(_GRADE_PATTERN.search(q))
    has_major_or_topic = "专业" in q or "ai" in q.lower() or "前端" in q or "后端" in q
    has_pace = "平时学习" in q or "周末集中" in q or "每天少量" in q or "高强度冲刺" in q
    has_separators = any(mark in q for mark in ("，", ",", "、", ";", "；"))
    return has_separators and (has_grade or has_major_or_topic or has_pace)


# ── Error extraction ─────────────────────────────────────────────────────

def _extract_last_error(state: dict) -> str:
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            try:
                content = (
                    json.loads(str(msg.content))
                    if isinstance(msg.content, str)
                    else msg.content
                )
                if isinstance(content, dict):
                    return content.get("error", "")
            except (json.JSONDecodeError, TypeError):
                pass
            break
    return ""


def _extract_last_tool_agent(state: dict) -> str:
    messages = state.get("messages", [])

    for index in range(len(messages) - 1, -1, -1):
        msg = messages[index]
        if isinstance(msg, ToolMessage):
            tool_call_id = msg.tool_call_id
            for previous in range(index - 1, -1, -1):
                prev_msg = messages[previous]
                if isinstance(prev_msg, AIMessage):
                    for tool_call in reversed(prev_msg.tool_calls or []):
                        if tool_call.get("id") == tool_call_id:
                            return str(tool_call.get("name", ""))
            return ""
    return ""


def _latest_ai_text(state: dict) -> str:
    messages = state.get("messages", [])

    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            continue
        if isinstance(msg, HumanMessage):
            continue
        if not isinstance(msg, AIMessage):
            continue

        content = msg.content
        if not isinstance(content, str):
            continue
        text = content.strip()
        if text:
            return text

    return ""


def has_pending_profile_update_followup(state: dict) -> bool:
    latest_ai_text = _latest_ai_text(state)
    if not latest_ai_text:
        return False
    return latest_ai_text.startswith(_COMPLETED_REPLAN_RESPONSE_PREFIX) or latest_ai_text.startswith(
        _PROFILE_UPDATE_PROMPT_PREFIX
    )


def should_auto_continue_learning_path_after_profile(state: dict) -> bool:
    if _extract_last_tool_agent(state) != AGENT_PROFILE:
        return False
    if not has_pending_profile_update_followup(state):
        return False
    profile = state.get("profile", {})
    return _is_complete_profile(profile)


# ── Hard rule functions ──────────────────────────────────────────────────

def _is_complete_profile(profile: dict) -> bool:
    return is_complete_profile_data(profile)


def _has_learning_paths(state: dict) -> bool:
    year_learning_paths = state.get("year_learning_paths")
    if isinstance(year_learning_paths, dict) and year_learning_paths:
        return True
    learning_path = state.get("learning_path")
    return isinstance(learning_path, dict) and bool(learning_path)


def _has_course_knowledge(state: dict) -> bool:
    value = state.get("course_knowledge")
    return isinstance(value, dict) and bool(value.get("course_id"))


def _rule_no_profile(state: dict, profile: dict) -> RuleResult:
    """No completed profile → block path and course_knowledge agents."""
    result = RuleResult(
        blocked_agents={AGENT_LEARNING_PATH, AGENT_COURSE_KNOWLEDGE},
        allowed_agents={AGENT_PROFILE},
    )
    query = str(state.get("query", "")).strip()

    profile_type = profile.get("type", "") if isinstance(profile, dict) else ""
    if is_default_profile_query(query):
        result.force_call = AGENT_PROFILE
        result.system_hints.append(
            "[系统级强制指令] 用户明确要求按默认信息直接生成基础画像。"
            "你必须立即调用 profile_agent 生成可编辑画像，"
            "不要直接回复解释，也不要调用 learning_path_agent 或 course_knowledge_agent。"
        )
        return result
    if is_profile_refinement_query(query):
        result.force_call = AGENT_PROFILE
        result.system_hints.append(
            "[系统级强制指令] 用户正在提供基础画像信息。"
            "你必须立即调用 profile_agent 解析并保存画像，"
            "不要调用 learning_path_agent 或 course_knowledge_agent。"
        )
        return result
    if profile_type == "collecting":
        result.force_call = AGENT_PROFILE

    last_error = _extract_last_error(state)
    if last_error and any(kw in last_error for kw in ("profile", "画像", "生成失败", "无法被解析")):
        result.system_hints.append(
            "[系统级强制指令] profile_agent 上一次执行失败。不要再次调用 profile_agent。"
            "请直接告诉用户画像生成遇到了问题，建议用户尝试说「直接帮我生成默认的」来使用快速通道。"
        )
    else:
        result.system_hints.append(
            "[系统级强制指令] 用户尚未完成基础画像。"
            "你必须首先调用 profile_agent 生成画像，"
            "不要调用 learning_path_agent 或 course_knowledge_agent。"
        )

    return result


def _rule_has_profile_no_path(state: dict, profile: dict) -> RuleResult:
    """Has completed profile but no learning path → block course_knowledge."""
    result = RuleResult(
        allowed_agents={AGENT_PROFILE, AGENT_LEARNING_PATH},
        blocked_agents={AGENT_COURSE_KNOWLEDGE},
    )
    query = str(state.get("query", "")).strip()
    last_tool_agent = _extract_last_tool_agent(state)

    if should_auto_continue_learning_path_after_profile(state):
        result.force_call = AGENT_LEARNING_PATH
        result.system_hints.append(
            "[系统级强制指令] 用户刚完成画像更新，且上一轮要求在画像更新后重新生成学习路径。"
            "你必须立即调用 learning_path_agent，基于最新画像刷新学习路径。"
        )
        return result

    if last_tool_agent == AGENT_PROFILE:
        result.blocked_agents = {AGENT_LEARNING_PATH, AGENT_COURSE_KNOWLEDGE}
        result.allowed_agents = {AGENT_PROFILE}
        result.system_hints.append(
            "[系统级强制指令] profile_agent 刚在本轮生成完画像。"
            "这一轮不要继续调用 learning_path_agent。"
            "请直接向用户展示画像结果，并询问是否继续生成学习路径。"
        )
        return result

    if is_navigation_query(query) or is_learning_path_refresh_query(query):
        result.force_call = AGENT_LEARNING_PATH
        result.system_hints.append(
            "[系统级强制指令] 用户画像已完成但尚无学习路径，且用户正在请求下一步学习安排。"
            "你必须调用 learning_path_agent 生成学习路径，"
            "不要再次调用 profile_agent。"
        )
        return result

    if is_profile_refinement_query(query):
        result.force_call = AGENT_PROFILE
        result.system_hints.append(
            "[系统级强制指令] 用户正在补充或修正画像字段。"
            "你必须调用 profile_agent 更新画像，"
            "不要直接生成学习路径。"
        )
        return result
    if is_default_profile_query(query):
        result.force_call = AGENT_LEARNING_PATH
        result.system_hints.append(
            "[系统级强制指令] 用户要求基于当前画像直接生成学习路径。"
            "你必须调用 learning_path_agent，"
            "不要再次回到画像收集。"
        )
        return result

    result.system_hints.append(
        "[系统级强制指令] 用户画像已完成但没有学习路径。"
        "如果用户表达了想学什么，立即调用 learning_path_agent。"
        "不要调用 profile_agent（画像已完成）。"
        "不要调用 course_knowledge_agent（路径不存在）。"
    )

    return result


def _rule_has_profile_and_path(state: dict, profile: dict) -> RuleResult:
    """Has both profile and learning path → allow all, auto-navigate."""
    result = RuleResult()

    query = state.get("query", "").strip().lower()
    last_tool_agent = _extract_last_tool_agent(state)
    pending_profile_followup = has_pending_profile_update_followup(state)

    if should_auto_continue_learning_path_after_profile(state):
        result.force_call = AGENT_LEARNING_PATH
        result.system_hints.append(
            "[系统级强制指令] 用户刚完成画像更新，且当前流程要求在画像更新后重新生成学习路径。"
            "你必须立即调用 learning_path_agent，基于最新画像刷新学习路径。"
        )
        return result

    if last_tool_agent == AGENT_LEARNING_PATH:
        result.blocked_agents = {AGENT_PROFILE, AGENT_LEARNING_PATH, AGENT_COURSE_KNOWLEDGE}
        result.allowed_agents = set()
        result.system_hints.append(
            "[系统级强制指令] learning_path_agent 刚在本轮生成完学习路径。"
            "这一轮不要再次调用任何 agent。"
            "请直接向用户确认学习路径已生成，并引导用户开始第一门课程或先查看今日推荐。"
        )
        return result

    if last_tool_agent == AGENT_COURSE_KNOWLEDGE and is_course_resource_generation_query(query) and _has_course_knowledge(state):
        result.force_call = AGENT_SECTION_MARKDOWN
        result.system_hints.append(
            "[系统级强制指令] course_knowledge_agent 已为本轮资源请求生成课程大纲。"
            "你必须继续调用 section_markdown_agent，生成小节教学文档，"
            "后续由图自动串联视频搜索和 HTML 动画。"
        )
        return result

    if last_tool_agent == AGENT_COURSE_KNOWLEDGE:
        result.blocked_agents = {AGENT_PROFILE, AGENT_LEARNING_PATH, AGENT_COURSE_KNOWLEDGE}
        result.allowed_agents = set()
        result.system_hints.append(
            "[系统级强制指令] course_knowledge_agent 刚在本轮生成完课程大纲。"
            "这一轮不要再次调用任何 agent。"
            "请直接向用户展示课程大纲结果，并引导用户进入下一步学习。"
        )
        return result

    if pending_profile_followup and not (
        is_review_plan_query(query)
        or is_course_start_query(query)
        or is_course_change_query(query)
    ):
        result.force_call = AGENT_PROFILE
        result.system_hints.append(
            "[系统级强制指令] 当前会话正在处理“先更新个人画像，再重新生成学习路径”的后续动作。"
            "你必须先调用 profile_agent 更新画像；如果仍缺信息，直接向用户追问。"
        )
        return result

    if is_course_outline_regeneration_query(query):
        result.force_call = AGENT_COURSE_KNOWLEDGE
        result.system_hints.append(
            "[系统级强制指令] 用户明确要求重新生成当前课程大纲。"
            "你必须调用 course_knowledge_agent 刷新课程大纲，"
            "不要直接复述已有课程大纲。"
        )
        return result

    if is_course_resource_generation_query(query):
        if _has_course_knowledge(state):
            result.force_call = AGENT_SECTION_MARKDOWN
        else:
            result.force_call = AGENT_COURSE_KNOWLEDGE
            result.blocked_agents.add(AGENT_SECTION_MARKDOWN)
            result.blocked_agents.add(AGENT_SECTION_VIDEO_SEARCH)
            result.blocked_agents.add(AGENT_SECTION_HTML_ANIMATION)
        return result

    if is_navigation_query(query):
        result.system_hints.append(
            "[系统级强制指令] 画像和学习路径均已完成。用户表达了继续意愿，"
            "询问用户是否要开始第一门课程。"
        )
    elif is_course_start_query(query) or is_course_change_query(query):
        result.force_call = AGENT_COURSE_KNOWLEDGE
    elif is_profile_update_query(query) or is_profile_refinement_query(query):
        result.force_call = AGENT_PROFILE
        result.system_hints.append(
            "[系统级强制指令] 用户要更新已有画像。"
            "你必须调用 profile_agent 更新画像，"
            "不要直接开始课程，也不要直接复述旧学习路径。"
        )
    elif is_learning_path_refresh_query(query):
        result.force_call = AGENT_LEARNING_PATH
        result.system_hints.append(
            "[系统级强制指令] 用户要基于当前画像重新生成学习路径。"
            "你必须调用 learning_path_agent，"
            "不要直接开始课程。"
        )
    elif is_review_plan_query(query):
        result.blocked_agents = {AGENT_PROFILE, AGENT_LEARNING_PATH, AGENT_COURSE_KNOWLEDGE}
        result.allowed_agents = set()
        result.system_hints.append(
            "[系统级强制指令] 用户想回顾学习路径，直接回复概览信息即可，不要调用任何 agent。"
        )
    else:
        result.system_hints.append(
            "[系统级强制指令] 画像和学习路径均已完成。分析用户意图后决定下一步。"
            "如果用户想开始课程 → 调用 course_knowledge_agent。"
            "如果用户想看路径或闲聊 → 直接回复。"
            "不要重复展示画像或路径数据。"
        )

    return result


# ── Main evaluation ──────────────────────────────────────────────────────

def evaluate(state: dict) -> RuleResult:
    """Evaluate all hard rules against the current state."""
    profile = state.get("profile", {})

    has_completed_profile = _is_complete_profile(profile)
    has_year_learning_paths = _has_learning_paths(state)

    if not has_completed_profile:
        return _rule_no_profile(state, profile)

    if has_completed_profile and not has_year_learning_paths:
        return _rule_has_profile_no_path(state, profile)

    if has_completed_profile and has_year_learning_paths:
        return _rule_has_profile_and_path(state, profile)

    return RuleResult(
        system_hints=["[系统指令] 当前状态未知，尽你所能帮助用户。"]
    )


def build_blocked_agents_hint(blocked: set[str]) -> str:
    """Generate a system hint listing blocked agents."""
    if not blocked:
        return ""
    names = sorted(blocked)
    return f"[系统级强制指令] 以下工具当前不可调用：{', '.join(f'`{n}`' for n in names)}。"
