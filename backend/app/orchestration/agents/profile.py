from __future__ import annotations

import json
import logging
import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate

from app.orchestration.agents.models import ProfileOutput
from app.orchestration.agents.prompts import (
    PROFILE_AGENT_REPAIR_SYSTEM_PROMPT,
    PROFILE_AGENT_SYSTEM_PROMPT,
)
from app.orchestration.agents.utils import (
    extract_last_tool_call_args,
    extract_last_tool_call_id,
)
from app.orchestration.default_fill import allows_default_profile_fill
from app.orchestration.grade_contract import (
    is_supported_current_grade,
    unsupported_current_grade_error,
)
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)

REQUIRED_CONFIRMED_INFO_KEYS = frozenset(
    {
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
    }
)
PROFILE_COMPLETION_REQUIRED_KEYS = frozenset(
    {
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
    }
)
UNKNOWN_VALUE = "未知"
DEFAULT_GRADE = "大三"
DEFAULT_MAJOR = "软件工程"
AI_TOPIC = "AI 应用开发"
DEFAULT_TOPIC = ""
GRADE_PATTERN = re.compile(r"(大[一二三四]|大[1234]|[一二三四]年级|研[一二三])")
ENGLISH_GRADE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bfreshman\b", re.IGNORECASE), "大一"),
    (re.compile(r"\bsophomore\b", re.IGNORECASE), "大二"),
    (re.compile(r"\bthird[\s-]?year\b", re.IGNORECASE), "大三"),
    (re.compile(r"\bjunior\b", re.IGNORECASE), "大三"),
    (re.compile(r"\bfourth[\s-]?year\b", re.IGNORECASE), "大四"),
    (re.compile(r"\bsenior\b", re.IGNORECASE), "大四"),
)
SPLIT_PATTERN = re.compile(r"[，,、；;／/\s]+")
EXPLICIT_FIELD_SPLIT_PATTERN = re.compile(r"[，,、；;]+")
PACE_SEGMENTS = {"平时学习", "周末集中", "每天少量", "高强度冲刺"}
GREETING_SEGMENTS = frozenset({"你好"})
CONTENT_PREFERENCE_SEGMENTS: tuple[tuple[str, list[str]], ...] = (
    ("喜欢看文档", ["文档"]),
    ("看文档", ["文档"]),
    ("喜欢文档", ["文档"]),
    ("喜欢视频", ["视频"]),
    ("看视频", ["视频"]),
    ("喜欢代码实践", ["代码实践"]),
    ("代码实践", ["代码实践"]),
    ("喜欢项目案例", ["项目案例"]),
    ("项目案例", ["项目案例"]),
)
GUIDANCE_PREFERENCE_SEGMENTS: tuple[tuple[str, str], ...] = (
    ("一步一步跟着操作", "需要强引导"),
    ("跟着操作", "需要强引导"),
    ("一步一步", "需要强引导"),
    ("喜欢自己摸索", "更喜欢自主探索"),
    ("自己摸索", "更喜欢自主探索"),
    ("自主学习", "更喜欢自主探索"),
    ("自学", "更喜欢自主探索"),
)
ENGLISH_MAJOR_BLOCKLIST = frozenset(
    {
        "hello",
        "working",
        "student",
        "engineering",
        "software",
        "third-year",
        "third",
        "year",
    }
)
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
    "小时",
    "小時",
    "分钟",
    "分鐘",
    "每周",
    "每天",
    "投入",
    "不知道怎么学",
    "怎么学",
)
LEARNING_METHOD_SEGMENTS = ("喜欢自己摸索", "自己摸索", "自主学习", "自学")
LEARNING_PREFERENCE_BLOCKED_SEGMENTS = ("喜欢看", "一步一步", "跟着操作")
GOAL_SEGMENTS = ("找工作", "就业", "实习", "考研")
TOPIC_PREFIXES = ("想学习", "想学", "学习", "学")
TOPIC_BLOCKED_VALUES = frozenset(
    {"", "路径", "学习路径", "课程", "画像", "什么", "下一步"}
)
TOPIC_TEXT_PATTERN = re.compile(
    r"(?P<prefix>想学习|想学|学习|学)(?P<topic>[^，,、；;／/。！？!?\n]+)"
)
TOPIC_BOUNDARY_CHARS = frozenset("，,、；;／/。！？!?\n ")
NARRATIVE_PUNCTUATION = ("。", "？", "?", "！", "!", "\n")
BRIEF_PROFILE_SEGMENT_LIMIT = 8
BRIEF_PROFILE_SEGMENT_LENGTH_LIMIT = 18
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
ASCII_TOKEN_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
NUMERIC_SEGMENT_PATTERN = re.compile(r"^\d+(?:[-~—]\d+)?$")
PROFILE_REPAIR_MAX_ATTEMPTS = 3

_FIELD_QUESTIONS: dict[str, dict[str, object]] = {
    "learning_stage": {
        "question": "你目前的学习阶段是？",
        "stage": "learning_preference",
        "options": [
            {
                "label": "有基础",
                "value": "有基础",
                "description": "已学过相关课程，有一定基础",
                "target_fields": ["learning_stage"],
                "fills": {"learning_stage": "有基础"},
            },
            {
                "label": "刚入门",
                "value": "刚入门",
                "description": "刚开始接触这个领域",
                "target_fields": ["learning_stage"],
                "fills": {"learning_stage": "刚入门"},
            },
            {
                "label": "项目实践",
                "value": "项目实践",
                "description": "已有项目经验，想进一步提升",
                "target_fields": ["learning_stage"],
                "fills": {"learning_stage": "项目实践"},
            },
            {
                "label": "准备就业",
                "value": "准备就业",
                "description": "即将毕业，以就业为导向",
                "target_fields": ["learning_stage"],
                "fills": {"learning_stage": "准备就业"},
            },
            {
                "label": "其他",
                "value": "__free_text__",
                "description": "以上都不符合，我来输入",
                "target_fields": [],
                "fills": {},
            },
        ],
    },
    "has_clear_goal": {
        "question": "你的学习目标清晰吗？",
        "stage": "learning_preference",
        "options": [
            {
                "label": "目标明确",
                "value": "是",
                "description": "清楚自己要学什么",
                "target_fields": ["has_clear_goal"],
                "fills": {"has_clear_goal": "是"},
            },
            {
                "label": "大致有方向",
                "value": "大致有方向",
                "description": "知道大方向，细节待定",
                "target_fields": ["has_clear_goal"],
                "fills": {"has_clear_goal": "大致有方向"},
            },
            {
                "label": "还没想好",
                "value": "否",
                "description": "需要帮助探索方向",
                "target_fields": ["has_clear_goal"],
                "fills": {"has_clear_goal": "否"},
            },
            {
                "label": "其他",
                "value": "__free_text__",
                "description": "以上都不符合，我来输入",
                "target_fields": [],
                "fills": {},
            },
        ],
    },
    "learning_method_preference": {
        "question": "你偏好哪种学习方式？",
        "stage": "learning_preference",
        "options": [
            {
                "label": "项目驱动学习",
                "value": "项目驱动学习",
                "description": "通过做项目来学",
                "target_fields": ["learning_method_preference"],
                "fills": {"learning_method_preference": "项目驱动学习"},
            },
            {
                "label": "系统课程学习",
                "value": "系统课程学习",
                "description": "按课程体系系统学习",
                "target_fields": ["learning_method_preference"],
                "fills": {"learning_method_preference": "系统课程学习"},
            },
            {
                "label": "AI 交互式学习",
                "value": "AI 交互式学习",
                "description": "通过与 AI 对话来学习",
                "target_fields": ["learning_method_preference"],
                "fills": {"learning_method_preference": "AI 交互式学习"},
            },
            {
                "label": "刷题巩固",
                "value": "刷题巩固",
                "description": "通过大量练习来掌握",
                "target_fields": ["learning_method_preference"],
                "fills": {"learning_method_preference": "刷题巩固"},
            },
            {
                "label": "其他",
                "value": "__free_text__",
                "description": "以上都不符合，我来输入",
                "target_fields": [],
                "fills": {},
            },
        ],
    },
    "learning_pace_preference": {
        "question": "你希望什么学习节奏？",
        "stage": "learning_preference",
        "options": [
            {
                "label": "每天少量",
                "value": "每天少量",
                "description": "每天 1-2 小时",
                "target_fields": ["learning_pace_preference"],
                "fills": {"learning_pace_preference": "每天少量"},
            },
            {
                "label": "周末集中",
                "value": "周末集中",
                "description": "周末集中学习",
                "target_fields": ["learning_pace_preference"],
                "fills": {"learning_pace_preference": "周末集中"},
            },
            {
                "label": "按项目里程碑推进",
                "value": "按项目里程碑推进",
                "description": "按项目进度灵活安排",
                "target_fields": ["learning_pace_preference"],
                "fills": {"learning_pace_preference": "按项目里程碑推进"},
            },
            {
                "label": "高强度冲刺",
                "value": "高强度冲刺",
                "description": "短期内集中大量学习",
                "target_fields": ["learning_pace_preference"],
                "fills": {"learning_pace_preference": "高强度冲刺"},
            },
            {
                "label": "其他",
                "value": "__free_text__",
                "description": "以上都不符合，我来输入",
                "target_fields": [],
                "fills": {},
            },
        ],
    },
    "content_preference": {
        "question": "你偏好什么内容形式？",
        "stage": "learning_preference",
        "options": [
            {
                "label": "文档为主",
                "value": "文档",
                "description": "喜欢阅读文档学习",
                "target_fields": ["content_preference"],
                "fills": {"content_preference": ["文档"]},
            },
            {
                "label": "视频为主",
                "value": "视频",
                "description": "喜欢看视频学习",
                "target_fields": ["content_preference"],
                "fills": {"content_preference": ["视频"]},
            },
            {
                "label": "代码实践为主",
                "value": "代码实践",
                "description": "喜欢通过写代码学习",
                "target_fields": ["content_preference"],
                "fills": {"content_preference": ["代码实践"]},
            },
            {
                "label": "项目案例为主",
                "value": "项目案例",
                "description": "喜欢通过完整项目学习",
                "target_fields": ["content_preference"],
                "fills": {"content_preference": ["项目案例"]},
            },
            {
                "label": "其他",
                "value": "__free_text__",
                "description": "以上都不符合，我来输入",
                "target_fields": [],
                "fills": {},
            },
        ],
    },
    "need_guidance": {
        "question": "你需要什么程度的引导？",
        "stage": "learning_preference",
        "options": [
            {
                "label": "需要强引导",
                "value": "需要强引导",
                "description": "希望有详细步骤指导",
                "target_fields": ["need_guidance"],
                "fills": {"need_guidance": "需要强引导"},
            },
            {
                "label": "需要轻量提醒",
                "value": "需要轻量提醒",
                "description": "偶尔需要关键节点提醒",
                "target_fields": ["need_guidance"],
                "fills": {"need_guidance": "需要轻量提醒"},
            },
            {
                "label": "更喜欢自主探索",
                "value": "更喜欢自主探索",
                "description": "自己摸索为主",
                "target_fields": ["need_guidance"],
                "fills": {"need_guidance": "更喜欢自主探索"},
            },
            {
                "label": "其他",
                "value": "__free_text__",
                "description": "以上都不符合，我来输入",
                "target_fields": [],
                "fills": {},
            },
        ],
    },
    "knowledge_foundation": {
        "question": "你目前的知识基础是什么？",
        "stage": "ability_basis",
        "options": [
            {
                "label": "编程基础扎实",
                "value": "编程基础扎实",
                "description": "数据结构、算法、设计模式等掌握较好",
                "target_fields": ["knowledge_foundation"],
                "fills": {"knowledge_foundation": "编程基础扎实"},
            },
            {
                "label": "有前后端基础",
                "value": "有前后端基础",
                "description": "了解 Web 开发基本流程",
                "target_fields": ["knowledge_foundation"],
                "fills": {"knowledge_foundation": "有前后端基础"},
            },
            {
                "label": "有 Python 基础",
                "value": "有 Python 基础",
                "description": "能用 Python 写脚本和小工具",
                "target_fields": ["knowledge_foundation"],
                "fills": {"knowledge_foundation": "有 Python 基础"},
            },
            {
                "label": "其他",
                "value": "__free_text__",
                "description": "以上都不符合，我来输入",
                "target_fields": [],
                "fills": {},
            },
        ],
    },
    "strengths": {
        "question": "你的优势是什么？",
        "stage": "ability_basis",
        "options": [
            {
                "label": "动手能力强",
                "value": "动手能力强",
                "description": "善于从零开始做项目",
                "target_fields": ["strengths"],
                "fills": {"strengths": "动手能力强"},
            },
            {
                "label": "学习能力强",
                "value": "学习能力强",
                "description": "能快速掌握新技术",
                "target_fields": ["strengths"],
                "fills": {"strengths": "学习能力强"},
            },
            {
                "label": "逻辑思维好",
                "value": "逻辑思维好",
                "description": "善于分析和拆解问题",
                "target_fields": ["strengths"],
                "fills": {"strengths": "逻辑思维好"},
            },
            {
                "label": "其他",
                "value": "__free_text__",
                "description": "以上都不符合，我来输入",
                "target_fields": [],
                "fills": {},
            },
        ],
    },
    "weaknesses": {
        "question": "你的薄弱点是什么？",
        "stage": "ability_basis",
        "options": [
            {
                "label": "缺少项目经验",
                "value": "缺少项目经验",
                "description": "理论知识有但实战少",
                "target_fields": ["weaknesses"],
                "fills": {"weaknesses": "缺少项目经验"},
            },
            {
                "label": "缺少系统训练",
                "value": "缺少系统训练",
                "description": "知识比较零散",
                "target_fields": ["weaknesses"],
                "fills": {"weaknesses": "缺少系统训练"},
            },
            {
                "label": "调试能力不足",
                "value": "调试能力不足",
                "description": "遇到问题不知从何排查",
                "target_fields": ["weaknesses"],
                "fills": {"weaknesses": "调试能力不足"},
            },
            {
                "label": "其他",
                "value": "__free_text__",
                "description": "以上都不符合，我来输入",
                "target_fields": [],
                "fills": {},
            },
        ],
    },
    "experience": {
        "question": "你有什么相关经验？",
        "stage": "ability_basis",
        "options": [
            {
                "label": "有课程项目经验",
                "value": "有课程项目经验",
                "description": "做过课程设计或大作业",
                "target_fields": ["experience"],
                "fills": {"experience": "有课程项目经验"},
            },
            {
                "label": "有实习经验",
                "value": "有实习经验",
                "description": "参加过企业实习",
                "target_fields": ["experience"],
                "fills": {"experience": "有实习经验"},
            },
            {
                "label": "有个人项目经验",
                "value": "有个人项目经验",
                "description": "自己做过独立项目",
                "target_fields": ["experience"],
                "fills": {"experience": "有个人项目经验"},
            },
            {
                "label": "其他",
                "value": "__free_text__",
                "description": "以上都不符合，我来输入",
                "target_fields": [],
                "fills": {},
            },
        ],
    },
    "short_term_goal": {
        "question": "你的近期目标是什么？",
        "stage": "learning_preference",
        "options": [
            {
                "label": "找工作",
                "value": "找工作",
                "description": "以就业为近期目标",
                "target_fields": ["short_term_goal"],
                "fills": {"short_term_goal": "找工作"},
            },
            {
                "label": "考研",
                "value": "考研",
                "description": "以考研为近期目标",
                "target_fields": ["short_term_goal"],
                "fills": {"short_term_goal": "考研"},
            },
            {
                "label": "提升能力",
                "value": "提升能力",
                "description": "以提升技术能力为目标",
                "target_fields": ["short_term_goal"],
                "fills": {"short_term_goal": "提升能力"},
            },
            {
                "label": "完成一个项目",
                "value": "完成一个项目",
                "description": "做出一个可运行的作品",
                "target_fields": ["short_term_goal"],
                "fills": {"short_term_goal": "完成一个项目"},
            },
            {
                "label": "其他",
                "value": "__free_text__",
                "description": "以上都不符合，我来输入",
                "target_fields": [],
                "fills": {},
            },
        ],
    },
    "long_term_goal": {
        "question": "你的长期目标是什么？",
        "stage": "goal_constraint",
        "options": [
            {
                "label": "成为全栈开发者",
                "value": "成为全栈开发者",
                "description": "前后端都能独立完成",
                "target_fields": ["long_term_goal"],
                "fills": {"long_term_goal": "成为全栈开发者"},
            },
            {
                "label": "成为 AI 应用开发者",
                "value": "成为 AI 应用开发者",
                "description": "专注于 AI 应用方向",
                "target_fields": ["long_term_goal"],
                "fills": {"long_term_goal": "成为 AI 应用开发者"},
            },
            {
                "label": "还没想好",
                "value": "还没想好",
                "description": "先学着再说",
                "target_fields": ["long_term_goal"],
                "fills": {"long_term_goal": "还没想好"},
            },
            {
                "label": "其他",
                "value": "__free_text__",
                "description": "以上都不符合，我来输入",
                "target_fields": [],
                "fills": {},
            },
        ],
    },
    "weekly_available_time": {
        "question": "每周可投入多少时间学习？",
        "stage": "learning_preference",
        "options": [
            {
                "label": "每周 6-10 小时",
                "value": "每周 6-10 小时",
                "description": "中等投入",
                "target_fields": ["weekly_available_time"],
                "fills": {"weekly_available_time": "每周 6-10 小时"},
            },
            {
                "label": "每周 10-15 小时",
                "value": "每周 10-15 小时",
                "description": "较高投入",
                "target_fields": ["weekly_available_time"],
                "fills": {"weekly_available_time": "每周 10-15 小时"},
            },
            {
                "label": "每周 15 小时以上",
                "value": "每周 15 小时以上",
                "description": "高强度投入",
                "target_fields": ["weekly_available_time"],
                "fills": {"weekly_available_time": "每周 15 小时以上"},
            },
            {
                "label": "其他",
                "value": "__free_text__",
                "description": "以上都不符合，我来输入",
                "target_fields": [],
                "fills": {},
            },
        ],
    },
    "constraints": {
        "question": "你有什么主要约束或限制？",
        "stage": "goal_constraint",
        "options": [
            {
                "label": "平时课程多",
                "value": "平时课程多",
                "description": "学期中时间紧张",
                "target_fields": ["constraints"],
                "fills": {"constraints": "平时课程多"},
            },
            {
                "label": "缺少指导",
                "value": "缺少指导",
                "description": "没有合适的引路人",
                "target_fields": ["constraints"],
                "fills": {"constraints": "缺少指导"},
            },
            {
                "label": "没有特别约束",
                "value": "没有特别约束",
                "description": "时间精力都比较充裕",
                "target_fields": ["constraints"],
                "fills": {"constraints": "没有特别约束"},
            },
            {
                "label": "其他",
                "value": "__free_text__",
                "description": "以上都不符合，我来输入",
                "target_fields": [],
                "fills": {},
            },
        ],
    },
}

_COLLECTING_FIELD_ORDER = (
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
)

_COLLECTING_STAGES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "learning_preference",
        "为了更好地为你定制学习路径，请填写你的学习偏好。",
        (
            "learning_stage",
            "has_clear_goal",
            "short_term_goal",
            "learning_method_preference",
            "learning_pace_preference",
            "content_preference",
            "need_guidance",
            "weekly_available_time",
        ),
    ),
    (
        "ability_basis",
        "为了评估你的学习起点，请完善你的能力基础。",
        (
            "knowledge_foundation",
            "experience",
            "strengths",
            "weaknesses",
        ),
    ),
    (
        "goal_constraint",
        "为了合理规划学习进度，请完善你的长期目标与约束。",
        (
            "long_term_goal",
            "constraints",
        ),
    ),
)

_AUTO_DEFAULT_FIELDS: frozenset[str] = frozenset(
    {
        "content_preference",
        "need_guidance",
        "learning_pace_preference",
        "weekly_available_time",
        "long_term_goal",
        "constraints",
    }
)


def _stage_missing_fields(
    merged: dict[str, object], stage_fields: tuple[str, ...]
) -> list[str]:
    missing: list[str] = []
    for field_name in stage_fields:
        value = merged.get(field_name)
        if field_name == "content_preference":
            if not isinstance(value, list) or not value:
                missing.append(field_name)
        elif not isinstance(value, str) or not value.strip():
            missing.append(field_name)
    return missing


def _build_stage_question_form(
    stage_name: str,
    stage_question: str,
    missing_fields: list[str],
) -> dict[str, object]:
    titles = {
        "learning_preference": "完善学习偏好",
        "ability_basis": "完善能力基础",
        "goal_constraint": "完善目标与约束",
    }
    descriptions = {
        "learning_preference": "请填写以下学习偏好信息，帮助我们更好地定制您的学习路径。",
        "ability_basis": "请填写以下能力基础信息，以便评估您的起点。",
        "goal_constraint": "请填写您的长期目标和约束，以合理规划学习进度。",
    }
    title = titles.get(stage_name, "完善画像信息")
    description = descriptions.get(stage_name, stage_question)

    questions = []
    for field_name in missing_fields:
        field_cfg = _FIELD_QUESTIONS.get(field_name)
        if not field_cfg:
            continue

        input_type = (
            "multi_choice" if field_name == "content_preference" else "single_choice"
        )

        questions.append(
            {
                "field_name": field_name,
                "label": field_cfg.get("question", ""),
                "description": "",
                "input_type": input_type,
                "required": True,
                "options": field_cfg.get("options", []),
            }
        )

    return {
        "title": title,
        "description": description,
        "stage": stage_name,
        "questions": questions,
        "submit_label": "提交",
    }


def _next_incomplete_field(confirmed_info: dict[str, object]) -> str | None:
    for field_name in _COLLECTING_FIELD_ORDER:
        value = confirmed_info.get(field_name)
        if field_name == "content_preference":
            if not isinstance(value, list) or not value:
                return field_name
        elif not isinstance(value, str) or not value.strip():
            return field_name
    return None


def _build_field_question_box(field_name: str) -> dict[str, object]:
    field = _FIELD_QUESTIONS[field_name]
    return {
        "question": str(field["question"]),
        "options": list(field["options"]),
    }


def _has_unknown_values(confirmed_info: dict[str, object]) -> bool:
    for key in PROFILE_COMPLETION_REQUIRED_KEYS:
        value = confirmed_info.get(key)
        if key == "content_preference":
            if not isinstance(value, list) or not value:
                return True
            if any(str(item).strip() in (UNKNOWN_VALUE, "") for item in value):
                return True
        elif (
            not isinstance(value, str)
            or not value.strip()
            or value.strip() == UNKNOWN_VALUE
        ):
            return True
    return False


def _missing_confirmed_info_fields(confirmed_info: dict[str, object]) -> list[str]:
    missing_fields: list[str] = []
    for key in PROFILE_COMPLETION_REQUIRED_KEYS:
        value = confirmed_info.get(key)
        if key == "content_preference":
            if not isinstance(value, list) or not value:
                missing_fields.append(key)
            continue
        if (
            not isinstance(value, str)
            or not value.strip()
            or value.strip() == UNKNOWN_VALUE
        ):
            missing_fields.append(key)
    return missing_fields


def _normalize_profile_output_dict(
    profile_dict: dict[str, object],
) -> dict[str, object]:
    normalized = dict(profile_dict)
    question_box = normalized.get("question_box")
    question_text = ""
    if isinstance(question_box, dict):
        question_text = str(question_box.get("question", "")).strip()
    question_md = str(normalized.get("question_md", "")).strip()
    text = str(normalized.get("text", "")).strip()
    summary_text = str(normalized.get("summary_text", "")).strip()

    if not question_md and question_text:
        normalized["question_md"] = question_text
    if not text and question_text:
        normalized["text"] = question_text
    elif not text and question_md:
        normalized["text"] = question_md
    elif text:
        normalized["text"] = text

    if not summary_text and str(normalized.get("type", "")).strip() == "basic_profile":
        text_value = str(normalized.get("text", "")).strip()
        if text_value:
            normalized["summary_text"] = text_value
    elif summary_text:
        normalized["summary_text"] = summary_text
        if not str(normalized.get("text", "")).strip():
            normalized["text"] = summary_text
    return normalized


def _profile_output_error(profile_dict: dict[str, object]) -> str | None:
    normalized = _normalize_profile_output_dict(profile_dict)
    profile_type = str(normalized.get("type", "")).strip()
    stage = str(normalized.get("stage", "")).strip()
    confirmed_info = normalized.get("confirmed_info")
    if not isinstance(confirmed_info, dict):
        return "confirmed_info 必须是对象"

    if profile_type == "basic_profile":
        if stage != "generated":
            return "basic_profile 的 stage 必须是 generated"
        missing_fields = _missing_confirmed_info_fields(confirmed_info)
        if missing_fields:
            return f"basic_profile 缺少完整字段：{', '.join(missing_fields)}"
        if not is_supported_current_grade(confirmed_info.get("current_grade")):
            return "basic_profile 的 current_grade 必须是大一到大四"
        if not str(normalized.get("text", "")).strip():
            return "basic_profile 缺少画像总结 text"
        question_box = normalized.get("question_box")
        if (
            not isinstance(question_box, dict)
            or not str(question_box.get("question", "")).strip()
        ):
            return "basic_profile 缺少下一步 question_box.question"
        return None

    if stage == "generated":
        return "collecting 的 stage 不能是 generated"
    question_box = normalized.get("question_box")
    question_text = (
        str(question_box.get("question", "")).strip()
        if isinstance(question_box, dict)
        else ""
    )
    question_md = str(normalized.get("question_md", "")).strip()
    text = str(normalized.get("text", "")).strip()
    if not any((question_text, question_md, text)):
        return "collecting 缺少下一轮问题内容"
    return None


def _is_complete_profile(profile: dict | None) -> bool:
    if not isinstance(profile, dict):
        return False
    if profile.get("type") != "basic_profile":
        return False
    confirmed_info = profile.get("confirmed_info")
    if not isinstance(confirmed_info, dict):
        return False
    return REQUIRED_CONFIRMED_INFO_KEYS.issubset(
        confirmed_info.keys()
    ) and is_supported_current_grade(confirmed_info.get("current_grade"))


def is_complete_profile_data(profile: dict | None) -> bool:
    return _is_complete_profile(profile)


def _allows_default_fill(text: str) -> bool:
    return allows_default_profile_fill(text)


def _message_content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _profile_context_payload(state: OrchestrationState) -> dict[str, object]:
    existing_profile = state.get("profile")
    confirmed = _empty_confirmed_info()

    if isinstance(existing_profile, dict):
        existing_confirmed = existing_profile.get("confirmed_info")
        if isinstance(existing_confirmed, dict):
            for key in confirmed:
                value = existing_confirmed.get(key)
                if key == "content_preference":
                    confirmed[key] = value if isinstance(value, list) else []
                elif isinstance(value, str):
                    confirmed[key] = value

    return {
        "type": str(existing_profile.get("type", ""))
        if isinstance(existing_profile, dict)
        else "",
        "stage": str(existing_profile.get("stage", ""))
        if isinstance(existing_profile, dict)
        else "",
        "question_mode": str(existing_profile.get("question_mode", ""))
        if isinstance(existing_profile, dict)
        else "",
        "question_md": str(existing_profile.get("question_md", ""))
        if isinstance(existing_profile, dict)
        else "",
        "text": str(existing_profile.get("text", ""))
        if isinstance(existing_profile, dict)
        else "",
        "confirmed_info": confirmed,
    }


def _build_profile_input(state: OrchestrationState, conversation_summary: str) -> str:
    messages = state.get("messages", [])
    recent_contents = [
        _message_content_text(getattr(message, "content", ""))
        for message in messages[-8:]
    ]
    query = state.get("query", "")
    allow_default_fill = _allows_default_fill(str(query))
    profile_context = json.dumps(
        _profile_context_payload(state), ensure_ascii=False, indent=2
    )

    parts = [
        "请根据以下基础画像上下文生成 SessionMessage JSON。",
        f"是否允许系统补全缺失字段：{'是' if allow_default_fill else '否'}。",
        "当前画像上下文：",
        profile_context,
        "主 Agent 对话总结：",
        conversation_summary,
        "最近对话内容：",
        "\n".join(content for content in recent_contents if content),
        "用户最新回复：",
        query,
    ]
    if allow_default_fill:
        parts.append("允许系统补全所有缺失字段。")
    parts.append("输出 SessionMessage JSON。")
    return "\n\n".join(part for part in parts if part)


def _build_profile_repair_input(
    state: OrchestrationState,
    conversation_summary: str,
    validation_error: str,
    previous_output: str,
) -> str:
    parts = [
        _build_profile_input(state, conversation_summary),
        "上一轮输出的问题：",
        validation_error,
    ]
    if previous_output.strip():
        parts.extend(
            [
                "上一轮无效输出：",
                previous_output,
            ]
        )
    parts.append("请输出修正后的 SessionMessage JSON。")
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


def _is_topic_text_match(match: re.Match[str], text: str) -> bool:
    prefix = match.group("prefix")
    if prefix in ("想学习", "想学"):
        return True
    return match.start() == 0 or text[match.start() - 1] in TOPIC_BOUNDARY_CHARS


def _ai_topic_from_text(text: str) -> str:
    if re.search(r"(?<![A-Za-z0-9])ai(?![A-Za-z0-9])", text, re.IGNORECASE):
        return AI_TOPIC
    return ""


def _topic_from_segment(segment: str) -> str:
    vibecoding_match = re.search(r"vibecoding", segment, re.IGNORECASE)
    if vibecoding_match:
        return vibecoding_match.group(0)

    for prefix in TOPIC_PREFIXES:
        if not segment.startswith(prefix):
            continue
        value = _clean_topic_value(segment[len(prefix) :])
        if value and value not in TOPIC_BLOCKED_VALUES:
            return value

    lowered = segment.lower()
    ai_topic = _ai_topic_from_text(lowered)
    if ai_topic:
        return ai_topic
    if "前端" in segment:
        return "前端开发"
    if "后端" in segment:
        return "后端开发"
    return ""


def _extract_topic(texts: list[str], segments: list[str]) -> str:
    for text in reversed(texts):
        for match in TOPIC_TEXT_PATTERN.finditer(text):
            if not _is_topic_text_match(match, text):
                continue
            topic = _clean_topic_value(match.group("topic"))
            if topic and topic not in TOPIC_BLOCKED_VALUES:
                return topic

    for segment in reversed(segments):
        topic = _topic_from_segment(segment)
        if topic:
            return topic

    for text in reversed(texts):
        ai_topic = _ai_topic_from_text(text)
        if ai_topic:
            return ai_topic
    if any("前端" in text for text in texts):
        return "前端开发"
    if any("后端" in text for text in texts):
        return "后端开发"
    return ""


def _topic_from_existing_profile(
    existing_profile: dict | None, existing_confirmed: dict
) -> str:
    content_preference = existing_confirmed.get("content_preference")
    content_text = (
        " ".join(str(item) for item in content_preference if str(item).strip())
        if isinstance(content_preference, list)
        else ""
    )
    confirmed_texts = [
        str(existing_confirmed.get("short_term_goal", "")),
        str(existing_confirmed.get("long_term_goal", "")),
        content_text,
    ]
    profile_texts: list[str] = []
    if isinstance(existing_profile, dict):
        profile_texts.extend(
            [
                str(existing_profile.get("summary_text", "")),
                str(existing_profile.get("text", "")),
            ]
        )

    segments = _normalize_segments(confirmed_texts)
    topic = _extract_topic(confirmed_texts, segments)
    if topic:
        return topic

    combined = "\n".join([*confirmed_texts, *profile_texts])
    if "vibecoding" in combined.lower():
        return "vibecoding"
    ai_topic = _ai_topic_from_text(combined)
    if ai_topic:
        return ai_topic
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


def _learning_stage_from_segment(segment: str) -> str:
    if any(marker in segment for marker in ("初学者", "刚入门", "新手", "零基础")):
        return "刚入门"
    if any(
        marker in segment
        for marker in ("有基础", "有一点基础", "有些基础", "有一定基础")
    ):
        return "有基础"
    if any(
        marker in segment for marker in ("项目实践", "做项目", "项目驱动", "边做边学")
    ):
        return "项目实践"
    if "准备就业" in segment:
        return "准备就业"
    return ""


def _content_preference_from_segment(segment: str) -> list[str]:
    for marker, values in CONTENT_PREFERENCE_SEGMENTS:
        if marker in segment:
            return list(values)
    return []


def _guidance_preference_from_segment(segment: str) -> str:
    for marker, value in GUIDANCE_PREFERENCE_SEGMENTS:
        if marker in segment:
            return value
    return ""


def _looks_like_learning_preference_segment(segment: str) -> bool:
    if _learning_stage_from_segment(segment):
        return True
    if _learning_method_from_segment(segment):
        return True
    if _content_preference_from_segment(segment):
        return True
    if _guidance_preference_from_segment(segment):
        return True
    return any(marker in segment for marker in LEARNING_PREFERENCE_BLOCKED_SEGMENTS)


def _goal_from_segment(segment: str) -> str:
    for marker in GOAL_SEGMENTS:
        if marker in segment:
            return marker
    return ""


def _english_grade_from_text(text: str) -> str:
    for pattern, grade in ENGLISH_GRADE_PATTERNS:
        if pattern.search(text):
            return grade
    return ""


def _clean_major_value(segment: str) -> str:
    value = segment.strip()
    if value.endswith("专业"):
        value = value[:-2]
    return _clean_explicit_field_value(value)


def _is_explicit_profile_field_segment(segment: str) -> bool:
    parts = re.split(r"[：:]", segment.strip(), maxsplit=1)
    return len(parts) == 2 and parts[0].strip() in REQUIRED_CONFIRMED_INFO_KEYS


def _major_from_segment(segment: str) -> str:
    value = _clean_major_value(segment)
    if not value:
        return ""
    if segment.strip().startswith(("画像表单提交：", "画像表单提交:")):
        return ""
    if _is_explicit_profile_field_segment(segment):
        return ""
    if len(value) > 16:
        return ""
    if NUMERIC_SEGMENT_PATTERN.fullmatch(value):
        return ""
    if ASCII_TOKEN_PATTERN.fullmatch(value):
        return ""
    lowered_value = value.lower()
    if lowered_value in ENGLISH_MAJOR_BLOCKLIST:
        return ""
    if (
        _topic_from_segment(segment)
        or _looks_like_learning_preference_segment(segment)
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


def _current_collecting_field(state: OrchestrationState) -> str:
    profile = state.get("profile")
    if not isinstance(profile, dict) or profile.get("type") != "collecting":
        return ""
    confirmed_info = profile.get("confirmed_info")
    if not isinstance(confirmed_info, dict):
        return ""

    missing_basic_fields = [
        field_name
        for field_name in ("current_grade", "major")
        if not isinstance(confirmed_info.get(field_name), str)
        or not str(confirmed_info.get(field_name)).strip()
    ]
    if len(missing_basic_fields) == 1:
        return missing_basic_fields[0]
    if len(missing_basic_fields) > 1:
        return ""

    next_field = _next_incomplete_field(confirmed_info)
    return next_field or ""


def _field_fill_from_options(field_name: str, text: str) -> dict[str, object]:
    field = _FIELD_QUESTIONS.get(field_name)
    if not field:
        return {}
    for option in field.get("options", []):
        if not isinstance(option, dict):
            continue
        value = str(option.get("value", "")).strip()
        label = str(option.get("label", "")).strip()
        if value == "__free_text__":
            continue
        if (label and label in text) or (value and value in text):
            fills = option.get("fills")
            if isinstance(fills, dict):
                return dict(fills)
    return {}


def _contextual_profile_updates(state: OrchestrationState) -> dict[str, object]:
    current_field = _current_collecting_field(state)
    query = str(state.get("query", "")).strip()
    if not current_field or not query:
        return {}

    if current_field == "current_grade":
        grade_match = GRADE_PATTERN.search(query)
        if grade_match:
            return {"current_grade": grade_match.group(1)}
        english_grade = _english_grade_from_text(query)
        return {"current_grade": english_grade} if english_grade else {}

    if current_field == "major":
        major = _major_from_segment(query)
        return {"major": major} if major else {}

    if current_field == "learning_stage":
        learning_stage = _learning_stage_from_segment(query)
        if learning_stage:
            return {"learning_stage": learning_stage}

    if current_field == "learning_method_preference":
        learning_method = _learning_method_from_segment(query)
        if learning_method:
            return {"learning_method_preference": learning_method}

    if current_field == "content_preference":
        content_preference = _content_preference_from_segment(query)
        if content_preference:
            return {"content_preference": content_preference}

    if current_field == "need_guidance":
        need_guidance = _guidance_preference_from_segment(query)
        if need_guidance:
            return {"need_guidance": need_guidance}

    return _field_fill_from_options(current_field, query)


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
        if normalized.startswith("画像表单提交：") or normalized.startswith(
            "画像表单提交:"
        ):
            lines = normalized.splitlines()
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = re.split(r"[：:]", line, maxsplit=1)
                if len(parts) == 2:
                    field_name = parts[0].strip()
                    field_value = parts[1].strip()
                    if field_name in REQUIRED_CONFIRMED_INFO_KEYS:
                        if field_name in updates:
                            continue
                        if not field_value:
                            continue
                        if field_name == "content_preference":
                            items = [
                                item.strip()
                                for item in re.split(r"[、，,]+", field_value)
                                if item.strip()
                            ]
                            updates[field_name] = items
                        else:
                            updates[field_name] = field_value
            continue

        # Existing logic for explicit prefixes
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
                    value = _clean_explicit_field_value(clause[len(prefix) :])
                    if value:
                        updates[field_name] = value
                    break
    return updates


def _looks_like_brief_profile_query(query: str) -> bool:
    normalized = query.strip()
    if not normalized:
        return False
    if _extract_explicit_profile_updates([normalized]):
        return True
    if any(mark in normalized for mark in NARRATIVE_PUNCTUATION):
        return False

    segments = _normalize_segments([normalized])
    if not 2 <= len(segments) <= BRIEF_PROFILE_SEGMENT_LIMIT:
        return False
    if any(len(segment) > BRIEF_PROFILE_SEGMENT_LENGTH_LIMIT for segment in segments):
        return False

    topic = _extract_topic([normalized], segments)
    return any(
        (
            bool(GRADE_PATTERN.search(normalized)),
            bool(_major_from_segments(segments)),
            bool(topic),
            any(segment in PACE_SEGMENTS for segment in segments),
            any(_learning_method_from_segment(segment) for segment in segments),
            any(_goal_from_segment(segment) for segment in segments),
        )
    )


def _extract_profile_updates(
    state: OrchestrationState, *, include_defaults: bool = True
) -> dict[str, object]:
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

        if "learning_stage" not in updates:
            learning_stage = _learning_stage_from_segment(segment)
            if learning_stage:
                updates["learning_stage"] = learning_stage
                continue

        if "content_preference" not in updates:
            content_preference = _content_preference_from_segment(segment)
            if content_preference:
                updates["content_preference"] = content_preference
                continue

        if "need_guidance" not in updates:
            need_guidance = _guidance_preference_from_segment(segment)
            if need_guidance:
                updates["need_guidance"] = need_guidance
                continue

        if not detected_goal:
            detected_goal = _goal_from_segment(segment)

    if "current_grade" not in updates:
        for text in reversed(texts):
            english_grade = _english_grade_from_text(text)
            if english_grade:
                updates["current_grade"] = english_grade
                break

    if "major" not in updates:
        major = _major_from_segments(segments)
        if major:
            updates["major"] = major

    if "short_term_goal" not in updates:
        short_term_goal = _short_term_goal_from_parts(detected_goal, topic)
        if short_term_goal:
            updates["short_term_goal"] = short_term_goal

    contextual_updates = _contextual_profile_updates(state)
    if contextual_updates:
        updates.update(contextual_updates)

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


def _collecting_profile_for_unsupported_grade(
    confirmed_info: dict[str, object],
) -> dict:
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
        "question_mode": "question_box",
        "confirmed_info": merged,
        "defaulted_fields": [],
        "question_md": question,
        "question_box": {
            "question": question,
            "options": [
                {
                    "label": "我是大一",
                    "value": "大一",
                    "description": "按本科大一继续生成画像",
                    "target_fields": ["current_grade"],
                    "fills": {"current_grade": "大一"},
                },
                {
                    "label": "我是大二",
                    "value": "大二",
                    "description": "按本科大二继续生成画像",
                    "target_fields": ["current_grade"],
                    "fills": {"current_grade": "大二"},
                },
                {
                    "label": "我是大三",
                    "value": "大三",
                    "description": "按本科大三继续生成画像",
                    "target_fields": ["current_grade"],
                    "fills": {"current_grade": "大三"},
                },
                {
                    "label": "我是大四",
                    "value": "大四",
                    "description": "按本科大四继续生成画像",
                    "target_fields": ["current_grade"],
                    "fills": {"current_grade": "大四"},
                },
                {
                    "label": "其他",
                    "value": "__free_text__",
                    "description": "以上都不符合，我来输入",
                    "target_fields": [],
                    "fills": {},
                },
            ],
        },
        "question_form": None,
        "text": question,
    }


def _build_basic_info_question_box(
    missing_fields: list[str], question: str
) -> dict[str, object]:
    options: list[dict[str, object]] = []
    if missing_fields == ["current_grade", "major"]:
        options = [
            {
                "label": "我是大一",
                "value": "大一",
                "description": "先确认年级，再继续补充专业",
                "target_fields": ["current_grade"],
                "fills": {"current_grade": "大一"},
            },
            {
                "label": "我是大二",
                "value": "大二",
                "description": "先确认年级，再继续补充专业",
                "target_fields": ["current_grade"],
                "fills": {"current_grade": "大二"},
            },
            {
                "label": "我是大三",
                "value": "大三",
                "description": "先确认年级，再继续补充专业",
                "target_fields": ["current_grade"],
                "fills": {"current_grade": "大三"},
            },
            {
                "label": "我是大四",
                "value": "大四",
                "description": "先确认年级，再继续补充专业",
                "target_fields": ["current_grade"],
                "fills": {"current_grade": "大四"},
            },
            {
                "label": "其他",
                "value": "__free_text__",
                "description": "以上都不符合，我来输入",
                "target_fields": [],
                "fills": {},
            },
        ]
    elif missing_fields == ["current_grade"]:
        options = [
            {
                "label": "大一",
                "value": "大一",
                "description": "当前是本科大一",
                "target_fields": ["current_grade"],
                "fills": {"current_grade": "大一"},
            },
            {
                "label": "大二",
                "value": "大二",
                "description": "当前是本科大二",
                "target_fields": ["current_grade"],
                "fills": {"current_grade": "大二"},
            },
            {
                "label": "大三",
                "value": "大三",
                "description": "当前是本科大三",
                "target_fields": ["current_grade"],
                "fills": {"current_grade": "大三"},
            },
            {
                "label": "大四",
                "value": "大四",
                "description": "当前是本科大四",
                "target_fields": ["current_grade"],
                "fills": {"current_grade": "大四"},
            },
            {
                "label": "其他",
                "value": "__free_text__",
                "description": "以上都不符合，我来输入",
                "target_fields": [],
                "fills": {},
            },
        ]
    elif missing_fields == ["major"]:
        options = [
            {
                "label": "计算机科学",
                "value": "计算机科学",
                "description": "常见计算机相关专业方向",
                "target_fields": ["major"],
                "fills": {"major": "计算机科学"},
            },
            {
                "label": "软件工程",
                "value": "软件工程",
                "description": "常见软件开发相关专业方向",
                "target_fields": ["major"],
                "fills": {"major": "软件工程"},
            },
            {
                "label": "人工智能",
                "value": "人工智能",
                "description": "常见 AI 相关专业方向",
                "target_fields": ["major"],
                "fills": {"major": "人工智能"},
            },
            {
                "label": "数据科学",
                "value": "数据科学",
                "description": "常见数据方向专业",
                "target_fields": ["major"],
                "fills": {"major": "数据科学"},
            },
            {
                "label": "其他",
                "value": "__free_text__",
                "description": "以上都不符合，我来输入",
                "target_fields": [],
                "fills": {},
            },
        ]
    return {"question": question, "options": options}


def _build_collecting_profile(state: OrchestrationState) -> dict:
    existing_profile = state.get("profile")
    existing_confirmed = (
        existing_profile.get("confirmed_info", {})
        if isinstance(existing_profile, dict)
        and isinstance(existing_profile.get("confirmed_info"), dict)
        else {}
    )
    updates = _extract_profile_updates(state, include_defaults=False)
    merged = _empty_confirmed_info()

    for key in merged:
        if key in updates and updates.get(key):
            merged[key] = updates[key]
        elif key in existing_confirmed and existing_confirmed.get(key):
            merged[key] = existing_confirmed[key]

    current_grade = merged.get("current_grade")
    if (
        isinstance(current_grade, str)
        and current_grade.strip()
        and not is_supported_current_grade(current_grade)
    ):
        return _collecting_profile_for_unsupported_grade(merged)

    missing_fields = [
        field_name
        for field_name in ("current_grade", "major")
        if not isinstance(merged.get(field_name), str)
        or not str(merged.get(field_name)).strip()
    ]

    if missing_fields == ["current_grade", "major"]:
        question = (
            "为了生成基础画像，请先告诉我你的年级和专业。"
            "如果你愿意，也可以一起告诉我想学的方向、近期目标和每周可投入时间。"
        )
        return {
            "type": "collecting",
            "stage": "basic_info",
            "question_mode": "question_box",
            "confirmed_info": merged,
            "defaulted_fields": [],
            "question_md": question,
            "question_box": _build_basic_info_question_box(missing_fields, question),
            "question_form": None,
            "text": question,
        }
    elif missing_fields == ["current_grade"]:
        question = "为了生成基础画像，请先告诉我你的年级。"
        return {
            "type": "collecting",
            "stage": "basic_info",
            "question_mode": "question_box",
            "confirmed_info": merged,
            "defaulted_fields": [],
            "question_md": question,
            "question_box": _build_basic_info_question_box(missing_fields, question),
            "question_form": None,
            "text": question,
        }
    elif missing_fields == ["major"]:
        question = "为了生成基础画像，请先告诉我你的专业。"
        return {
            "type": "collecting",
            "stage": "basic_info",
            "question_mode": "question_box",
            "confirmed_info": merged,
            "defaulted_fields": [],
            "question_md": question,
            "question_box": _build_basic_info_question_box(missing_fields, question),
            "question_form": None,
            "text": question,
        }

    for stage_name, stage_question, stage_fields in _COLLECTING_STAGES:
        missing = _stage_missing_fields(merged, stage_fields)
        if missing:
            form = _build_stage_question_form(stage_name, stage_question, missing)
            form_title = form["title"]
            form_desc = form["description"]
            question_md = f"### {form_title}\n{form_desc}"
            return {
                "type": "collecting",
                "stage": stage_name,
                "question_mode": "question_box",
                "confirmed_info": merged,
                "defaulted_fields": [],
                "question_md": question_md,
                "question_box": {
                    "question": form_title,
                    "options": [],
                },
                "question_form": form,
                "text": f"{form_title}：{form_desc}",
            }

    question = "画像信息已全部确认，可以生成完整画像了。"
    return {
        "type": "collecting",
        "stage": "basic_info",
        "question_mode": "question_md",
        "confirmed_info": merged,
        "defaulted_fields": [],
        "question_md": question,
        "question_box": {"question": "", "options": []},
        "question_form": None,
        "text": question,
    }


def _has_minimum_profile_fields(state: OrchestrationState) -> bool:
    existing_profile = state.get("profile")
    existing_confirmed = (
        existing_profile.get("confirmed_info", {})
        if isinstance(existing_profile, dict)
        and isinstance(existing_profile.get("confirmed_info"), dict)
        else {}
    )
    updates = _extract_profile_updates(state, include_defaults=False)
    current_grade = existing_confirmed.get("current_grade") or updates.get(
        "current_grade"
    )
    major = existing_confirmed.get("major") or updates.get("major")
    return (
        isinstance(current_grade, str)
        and current_grade.strip() != ""
        and isinstance(major, str)
        and major.strip() != ""
    )


def _missing_minimum_profile_fields(state: OrchestrationState) -> list[str]:
    existing_profile = state.get("profile")
    existing_confirmed = (
        existing_profile.get("confirmed_info", {})
        if isinstance(existing_profile, dict)
        and isinstance(existing_profile.get("confirmed_info"), dict)
        else {}
    )
    updates = _extract_profile_updates(state, include_defaults=False)
    missing: list[str] = []
    for key in ("current_grade", "major"):
        value = existing_confirmed.get(key) or updates.get(key)
        if not isinstance(value, str) or not value.strip():
            missing.append(key)
    return missing


def _can_complete_collecting_profile_locally(state: OrchestrationState) -> bool:
    profile = state.get("profile")
    if not isinstance(profile, dict) or profile.get("type") != "collecting":
        return False
    return _has_confirmed_profile_completion_fields(state)


def _has_confirmed_profile_completion_fields(state: OrchestrationState) -> bool:
    existing_profile = state.get("profile")
    existing_confirmed = (
        existing_profile.get("confirmed_info", {})
        if isinstance(existing_profile, dict)
        and isinstance(existing_profile.get("confirmed_info"), dict)
        else {}
    )
    updates = _extract_profile_updates(state, include_defaults=False)
    for key in PROFILE_COMPLETION_REQUIRED_KEYS:
        value = updates.get(key, existing_confirmed.get(key))
        if key == "content_preference":
            if not isinstance(value, list) or not value:
                return False
            continue
        if not isinstance(value, str) or not value.strip():
            return False
    return True


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
    updates: dict[str, object],
    *,
    topic: str,
    allow_default_fill: bool,
) -> list[object]:
    updates_content_preference = updates.get("content_preference")
    if isinstance(updates_content_preference, list) and updates_content_preference:
        return updates_content_preference
    existing_content_preference = existing_confirmed.get("content_preference")
    if isinstance(existing_content_preference, list) and existing_content_preference:
        return existing_content_preference
    if topic:
        return [topic]
    if allow_default_fill:
        return ["代码实践", "项目案例", "AI 对话调试"]
    return []


def _apply_profile_update_overrides(
    confirmed: dict[str, object], updates: dict[str, object]
) -> None:
    for key in REQUIRED_CONFIRMED_INFO_KEYS:
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
        if key not in updates
        and (
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
    default_short_term_goal = f"学习{topic}" if topic else "完成一个可运行的课程级项目"
    default_long_term_goal = (
        f"形成{topic}方向的系统学习能力" if topic else "形成系统学习能力"
    )

    def resolved(key: str, default_value: str = "") -> str:
        use_default = allow_default_fill or (not has_existing_complete_profile)
        return _resolved_profile_text(
            existing_confirmed,
            updates,
            key,
            allow_default_fill=use_default,
            default_value=default_value,
        )

    confirmed: dict[str, object] = {
        "current_grade": resolved(
            "current_grade", DEFAULT_GRADE if allow_default_fill else UNKNOWN_VALUE
        ),
        "major": resolved("major", DEFAULT_MAJOR),
        "learning_stage": resolved("learning_stage", "有基础"),
        "has_clear_goal": resolved("has_clear_goal", "大致有方向"),
        "learning_method_preference": resolved(
            "learning_method_preference", "项目驱动学习"
        ),
        "learning_pace_preference": resolved(
            "learning_pace_preference", "按项目里程碑推进"
        ),
        "content_preference": _resolved_content_preference(
            existing_confirmed,
            updates,
            topic=topic,
            allow_default_fill=allow_default_fill
            or (not has_existing_complete_profile),
        ),
        "need_guidance": resolved("need_guidance", "需要轻量提醒"),
        "knowledge_foundation": resolved("knowledge_foundation"),
        "strengths": resolved("strengths", "工程实现与课程学习能力"),
        "weaknesses": resolved(
            "weaknesses", "大型项目实战经验、数据库设计能力、英文阅读速度"
        ),
        "experience": resolved("experience", "平时学习"),
        "short_term_goal": resolved("short_term_goal", default_short_term_goal),
        "long_term_goal": resolved("long_term_goal", default_long_term_goal),
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
    if not confirmed["knowledge_foundation"] and (
        allow_default_fill
        or has_existing_complete_profile
        or not has_existing_complete_profile
    ):
        confirmed["knowledge_foundation"] = _generated_knowledge_foundation(
            confirmed.get("major"),
            topic,
        )
    return confirmed


def _build_local_profile(
    state: OrchestrationState, *, allow_default_fill: bool
) -> dict:
    existing_profile = state.get("profile")
    has_existing_complete_profile = _is_complete_profile(existing_profile)
    existing_confirmed = (
        existing_profile.get("confirmed_info", {})
        if isinstance(existing_profile, dict)
        and isinstance(existing_profile.get("confirmed_info"), dict)
        else {}
    )
    updates = _extract_profile_updates(state, include_defaults=allow_default_fill)
    topic = str(
        updates.pop("topic", DEFAULT_TOPIC if allow_default_fill else "")
    ).strip()
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
        allow_default_fill=allow_default_fill or (not has_existing_complete_profile),
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


def _has_minimum_dynamic_profile_fields(state: OrchestrationState) -> bool:
    existing_profile = state.get("profile")
    existing_confirmed = (
        existing_profile.get("confirmed_info", {})
        if isinstance(existing_profile, dict)
        and isinstance(existing_profile.get("confirmed_info"), dict)
        else {}
    )
    updates = _extract_profile_updates(state, include_defaults=False)

    def get_val(key: str) -> object:
        return updates.get(key, existing_confirmed.get(key))

    def is_valid_str(val: object) -> bool:
        return (
            isinstance(val, str) and val.strip() != "" and val.strip() != UNKNOWN_VALUE
        )

    current_grade = get_val("current_grade")
    major = get_val("major")
    learning_stage = get_val("learning_stage")
    has_clear_goal = get_val("has_clear_goal")
    learning_method_preference = get_val("learning_method_preference")
    weekly_available_time = get_val("weekly_available_time")
    short_term_goal = get_val("short_term_goal")

    if not (
        is_valid_str(current_grade)
        and is_valid_str(major)
        and is_valid_str(learning_stage)
        and is_valid_str(has_clear_goal)
        and is_valid_str(learning_method_preference)
        and is_valid_str(weekly_available_time)
        and is_valid_str(short_term_goal)
    ):
        return False

    knowledge_foundation = get_val("knowledge_foundation")
    experience = get_val("experience")

    return is_valid_str(knowledge_foundation) or is_valid_str(experience)


def _should_use_local_profile(state: OrchestrationState) -> bool:
    query = str(state.get("query", "")).strip()
    if _allows_default_fill(query):
        return True
    if _is_complete_profile(state.get("profile")):
        return True
    if _has_minimum_dynamic_profile_fields(state):
        return True
    if not query:
        return False
    if _has_confirmed_profile_completion_fields(state):
        return _looks_like_brief_profile_query(query)
    return False


def _fallback_collecting_profile(state: OrchestrationState) -> dict[str, object]:
    return _build_collecting_profile(state)


async def _invoke_profile_output_with_retries(
    state: OrchestrationState,
    llm: BaseChatModel,
    conversation_summary: str,
) -> dict[str, object]:
    structured_llm = llm.with_structured_output(ProfileOutput)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", PROFILE_AGENT_SYSTEM_PROMPT),
            ("human", "{profile_input}"),
        ]
    )
    repair_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", PROFILE_AGENT_REPAIR_SYSTEM_PROMPT),
            ("human", "{profile_input}"),
        ]
    )
    chain = prompt | structured_llm
    repair_chain = repair_prompt | structured_llm
    previous_output = ""
    validation_error = ""

    for attempt in range(PROFILE_REPAIR_MAX_ATTEMPTS):
        try:
            if attempt == 0:
                result: ProfileOutput = await chain.ainvoke(
                    {
                        "profile_input": _build_profile_input(
                            state, conversation_summary
                        ),
                    }
                )
            else:
                result = await repair_chain.ainvoke(
                    {
                        "profile_input": _build_profile_repair_input(
                            state,
                            conversation_summary,
                            validation_error,
                            previous_output,
                        ),
                    }
                )
        except Exception as exc:
            validation_error = str(exc)
            logger.warning(
                "ProfileAgent structured output attempt %s failed: %s", attempt + 1, exc
            )
            previous_output = ""
            continue

        profile_dict = _normalize_profile_output_dict(result.model_dump())
        previous_output = json.dumps(profile_dict, ensure_ascii=False)
        semantic_error = _profile_output_error(profile_dict)
        if semantic_error is None:
            return profile_dict

        validation_error = semantic_error
        logger.warning(
            "ProfileAgent semantic validation attempt %s failed: %s",
            attempt + 1,
            semantic_error,
        )

    logger.error(
        "ProfileAgent exhausted repair attempts; returning collecting fallback"
    )
    return _fallback_collecting_profile(state)


async def run_profile_agent(state: OrchestrationState, llm: BaseChatModel) -> dict:
    """One-shot profile generation: receives conversation summary, outputs structured profile."""
    tool_args = extract_last_tool_call_args(state)
    conversation_summary = tool_args.get("conversation_summary", state["query"])
    query = str(state.get("query", "")).strip()
    allow_default_fill = _allows_default_fill(query)
    updates = _extract_profile_updates(state, include_defaults=False)
    current_grade = updates.get("current_grade")
    if (
        not allow_default_fill
        and isinstance(current_grade, str)
        and current_grade.strip()
        and not is_supported_current_grade(current_grade)
    ):
        profile_dict = _build_collecting_profile(state)
    elif not allow_default_fill and _should_use_local_profile(state):
        profile_dict = _build_local_profile(state, allow_default_fill=False)
    else:
        profile_dict = await _invoke_profile_output_with_retries(
            state, llm, conversation_summary
        )
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
