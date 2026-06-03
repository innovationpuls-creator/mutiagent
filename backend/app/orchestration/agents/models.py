"""Simplified Pydantic output models for structured LLM generation.

Uses `with_structured_output` — no manual JSON parsing.
Models are permissive (no extra="forbid") to allow LLM flexibiliy.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Profile Agent ────────────────────────────────────────────────────────

class ProfileOutput(BaseModel):
    """画像 Agent 的结构化输出 — 用 with_structured_output 生成。"""
    current_grade: str = Field(description="当前年级，如 大一、大二")
    major: str = Field(description="所学专业")
    learning_stage: str = Field(description="学习阶段，如 刚入门、有基础")
    has_clear_goal: str = Field(description="是否有明确目标")
    learning_method_preference: str = Field(description="偏好学习方式")
    learning_pace_preference: str = Field(description="偏好学习节奏")
    content_preference: list[str] = Field(description="偏好内容形式")
    need_guidance: str = Field(description="引导需求程度")
    knowledge_foundation: str = Field(description="当前知识基础")
    strengths: str = Field(description="擅长方向")
    weaknesses: str = Field(description="薄弱方向")
    experience: str = Field(description="相关经验")
    short_term_goal: str = Field(description="近期目标")
    long_term_goal: str = Field(description="长期目标")
    weekly_available_time: str = Field(description="每周可投入时间")
    constraints: str = Field(description="主要困难和约束")
    summary_text: str = Field(description="自然语言画像总结")


# ── Learning Path Agent ──────────────────────────────────────────────────

class CourseItem(BaseModel):
    """单门课程 — 简版信息。"""
    course_id: str = Field(description="课程唯一 ID，如 year_2_course_1")
    course_name: str = Field(description="课程名称")
    description: str = Field(description="课程简介，1-2 句")
    semester: str = Field(description="学期：上学期/下学期/寒假/暑假")
    prerequisites: list[str] = Field(default_factory=list, description="前置课程 ID")
    estimated_duration: str = Field(description="预计时长")
    learning_goal: str = Field(description="学习目标")
    key_topics: list[str] = Field(description="核心知识点列表")


class YearLearningPathOutput(BaseModel):
    """某一年的学习路径 — 简版。"""
    grade_year: str = Field(description="年级 ID: year_1/year_2/year_3/year_4")
    grade_name: str = Field(description="年级名称，如 大二")
    grade_goal: str = Field(description="本年度总体目标")
    courses: list[CourseItem] = Field(description="推荐课程列表")
    recommended_sequence: list[str] = Field(description="推荐学习顺序，course_id 列表")
    personalization_notes: str = Field(description="个性化说明")


# ── Course Knowledge Agent ───────────────────────────────────────────────

class SectionItem(BaseModel):
    """章节/小节 — 详版定义。"""
    section_id: str = Field(description="节 ID，如 1, 1.1, 1.1.1")
    parent_section_id: str | None = Field(description="父节 ID，顶层为 null")
    depth: int = Field(ge=1, le=4, description="层级深度 1-4")
    title: str = Field(description="标题")
    order_index: int = Field(ge=1, description="排序索引")
    description: str = Field(default="", description="简要说明")
    key_knowledge_points: list[str] = Field(default_factory=list, description="核心知识点")


class CourseKnowledgeOutput(BaseModel):
    """课程大纲 — 详版。"""
    course_id: str = Field(description="课程 ID")
    course_name: str = Field(description="课程名称")
    grade_year: str = Field(description="所属年级")
    personalization_summary: str = Field(description="个性化安排说明")
    sections: list[SectionItem] = Field(description="章节列表，含层级关系")
    learning_sequence: list[str] = Field(description="推荐学习顺序，section_id 列表")
    total_estimated_hours: str = Field(description="预计总学时")
