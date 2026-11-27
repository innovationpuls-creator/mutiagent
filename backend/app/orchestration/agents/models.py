"""Pydantic models used by orchestration agents and local validation.

Some agents use structured LLM output. Course outline generation parses JSON
text and validates locally because the current production model does not
support structured output.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ── Profile Agent ────────────────────────────────────────────────────────

MAX_SOURCE_SECTION_COUNT = 7


# ── Learning Path Agent ──────────────────────────────────────────────────


# ── Course Knowledge Agent ───────────────────────────────────────────────


class SectionItem(BaseModel):
    """章节/小节 — 详版定义。"""

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(description="节 ID，如 1, 1.1, 1.1.1")
    parent_section_id: str | None = Field(description="父节 ID，顶层为 null")
    depth: int = Field(ge=1, le=4, description="层级深度 1-4")
    title: str = Field(description="标题")
    order_index: int = Field(ge=1, description="排序索引")
    description: str = Field(default="", description="简要说明")
    key_knowledge_points: list[str] = Field(
        min_length=1, description="章节内由课程大纲智能体设计的核心知识点"
    )
    source_textbook_id: str = Field(description="绑定教材 ID")
    source_textbook_title: str = Field(description="绑定教材标题")
    source_section_ids: list[str] = Field(
        min_length=1,
        description="绑定教材小节 ID",
    )
    source_section_titles: list[str] = Field(
        min_length=1,
        description="绑定教材小节标题",
    )
    source_content_chars: int = Field(ge=0, description="绑定教材正文字符数")
    source_chunk_index: int | None = Field(
        default=None, ge=1, description="超长教材小节被拆分后的分段序号（从 1 开始）"
    )
    source_chunk_total: int | None = Field(
        default=None, ge=2, description="超长教材小节被拆分成的分段总数"
    )
    source_char_range: list[int] | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="分段在教材小节正文中的字符区间 [起, 止)",
    )

    @field_validator(
        "section_id", "title", "source_textbook_id", "source_textbook_title"
    )
    @classmethod
    def require_text(cls, value: str, info) -> str:
        return _required_text(value, info.field_name)

    @field_validator(
        "key_knowledge_points", "source_section_ids", "source_section_titles"
    )
    @classmethod
    def require_text_list(cls, value: list[str], info) -> list[str]:
        return _require_text_list(value, info.field_name)

    @model_validator(mode="after")
    def validate_source_sections_length(self) -> "SectionItem":
        if self.depth > 1:
            if len(self.source_section_ids) > MAX_SOURCE_SECTION_COUNT:
                raise ValueError(
                    f"二级及以下章节最多绑定 {MAX_SOURCE_SECTION_COUNT} 个教材小节。"
                )
            if len(self.source_section_titles) > MAX_SOURCE_SECTION_COUNT:
                raise ValueError(
                    f"二级及以下章节最多绑定 {MAX_SOURCE_SECTION_COUNT} "
                    "个教材小节标题。"
                )
        return self


class CourseKnowledgeOutput(BaseModel):
    """课程大纲 — 详版。"""

    model_config = ConfigDict(extra="forbid")

    course_id: str = Field(description="课程 ID")
    course_name: str = Field(description="课程名称")
    grade_year: str = Field(description="所属年级")
    personalization_summary: str = Field(description="个性化安排说明")
    sections: list[SectionItem] = Field(description="章节列表，含层级关系")
    learning_sequence: list[str] = Field(
        description="推荐学习步骤，使用面向用户的自然语言短句列表"
    )
    total_estimated_hours: str = Field(description="预计总学时")


# ── Section Resource Agents ──────────────────────────────────────────────


def _required_text(value: str, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _require_text_list(value: list[str], field_name: str) -> list[str]:
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    normalized: list[str] = []
    for item in value:
        text = str(item).strip()
        if not text:
            raise ValueError(f"{field_name} must not contain empty items")
        normalized.append(text)
    return normalized
