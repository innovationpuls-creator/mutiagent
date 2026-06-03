"""Agent delegation rule engine.

Enforces hard rules (blocking) and provides soft hints for the supervisor LLM.
Hard rules gate which worker agents can be called based on system state.
Soft hints inject context into the supervisor's system prompt to guide LLM decisions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

# ── Agent keys ───────────────────────────────────────────────────────────
AGENT_PROFILE = "profile_agent"
AGENT_LEARNING_PATH = "learning_path_agent"
AGENT_COURSE_KNOWLEDGE = "course_knowledge_agent"

ALL_WORKER_AGENTS = {AGENT_PROFILE, AGENT_LEARNING_PATH, AGENT_COURSE_KNOWLEDGE}

# Keywords for intent detection
_NAVIGATION_QUERIES = {
    "下一步", "然后", "接下来", "继续", "好的", "ok", "好", "嗯", "哦", "好了",
}
_COURSE_START_KEYWORDS = {
    "start_first_course", "开始第一门课", "开始课程", "开始学习", "生成课程",
}
_REVIEW_PLAN_KEYWORDS = {
    "review_plan", "先看看学习路径", "看看路径", "回顾规划", "先看看",
}


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
    return any(kw in q for kw in _NAVIGATION_QUERIES)

def is_course_start_query(query: str) -> bool:
    q = query.strip().lower()
    return any(kw in q for kw in _COURSE_START_KEYWORDS)

def is_review_plan_query(query: str) -> bool:
    q = query.strip().lower()
    return any(kw in q for kw in _REVIEW_PLAN_KEYWORDS)


# ── Error extraction ─────────────────────────────────────────────────────

def _extract_last_error(state: dict) -> str:
    messages = state.get("messages", [])
    from langchain_core.messages import ToolMessage
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


# ── Hard rule functions ──────────────────────────────────────────────────

def _rule_no_profile(state: dict, profile: dict) -> RuleResult:
    """No completed profile → block path and course_knowledge agents."""
    result = RuleResult(
        blocked_agents={AGENT_LEARNING_PATH, AGENT_COURSE_KNOWLEDGE},
        allowed_agents={AGENT_PROFILE},
    )

    profile_type = profile.get("type", "") if isinstance(profile, dict) else ""
    if profile_type == "collecting":
        result.force_call = AGENT_PROFILE
        result.system_hints.append(
            "[系统级强制指令] 当前正处于 profile_agent 的信息收集中。"
            "无论用户说了什么（包括「直接生成」「跳过」「下一步」等），你都必须调用 profile_agent，"
            "将用户的最新回答通过 query 参数传给它。千万不要自己直接回答用户。"
        )
        return result

    last_error = _extract_last_error(state)
    if last_error and any(kw in last_error for kw in ("profile", "画像", "生成失败", "无法被解析")):
        result.system_hints.append(
            "[系统级强制指令] profile_agent 上一次执行失败。不要再次调用 profile_agent。"
            "请直接告诉用户画像生成遇到了问题，建议用户尝试说「直接帮我生成默认的」来使用快速通道。"
        )
    else:
        result.system_hints.append(
            "[系统级强制指令] 用户尚未完成基础画像。"
            "你必须首先调用 profile_agent 收集画像信息，"
            "不要调用 learning_path_agent 或 course_knowledge_agent。"
        )

    return result


def _rule_has_profile_no_path(state: dict, profile: dict) -> RuleResult:
    """Has completed profile but no learning path → block course_knowledge."""
    result = RuleResult(
        allowed_agents={AGENT_PROFILE, AGENT_LEARNING_PATH},
        blocked_agents={AGENT_COURSE_KNOWLEDGE},
    )

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

    if is_navigation_query(query):
        result.system_hints.append(
            "[系统级强制指令] 画像和学习路径均已完成。用户表达了继续意愿，"
            "询问用户是否要开始第一门课程。"
        )
    elif is_course_start_query(query):
        result.force_call = AGENT_COURSE_KNOWLEDGE
    elif is_review_plan_query(query):
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
    learning_path = state.get("learning_path")

    profile_type = profile.get("type", "") if isinstance(profile, dict) else ""
    has_completed_profile = profile_type == "basic_profile"
    has_learning_path = learning_path is not None

    if not has_completed_profile:
        return _rule_no_profile(state, profile)

    if has_completed_profile and not has_learning_path:
        return _rule_has_profile_no_path(state, profile)

    if has_completed_profile and has_learning_path:
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
