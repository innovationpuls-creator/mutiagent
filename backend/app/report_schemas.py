"""Public report payloads and bounded model output contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ReportStats(BaseModel):
    passed_chapters: int
    tested_chapters: int
    attempts: int


class ReportEvidence(BaseModel):
    id: str
    kind: Literal["path", "quiz", "chapter", "weakness", "textbook"]
    title: str
    detail: str
    course_id: str | None = None


class ReportInsight(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=900)
    evidence_ids: list[str] = Field(
        min_length=1,
        max_length=5,
        description="逐字复制本次 evidence 目录中 id 字段的值，不加前缀，不改写。",
    )


class ReportAction(ReportInsight):
    check: str = Field(min_length=1, max_length=300)
    course_id: str | None = Field(
        default=None, description="逐字复制 course_ids 中的值，或 null。"
    )


class ReportNarrative(BaseModel):
    overview: str = Field(min_length=1, max_length=1600)
    strengths: list[ReportInsight] = Field(max_length=3)
    improvements: list[ReportInsight] = Field(max_length=3)
    actions: list[ReportAction] = Field(max_length=3)


class GrowthReport(ReportNarrative):
    generated_at: datetime
    stats: ReportStats
    evidence: list[ReportEvidence]
    coverage: str


class ReportStage(BaseModel):
    stage: Literal["collecting", "analyzing", "writing"]


class ReportError(BaseModel):
    message: str


class EvidenceRequest(BaseModel):
    tool: Literal["read_quiz", "read_chapter", "read_textbook"]
    evidence_id: str


class EvidenceSelection(BaseModel):
    requests: list[EvidenceRequest] = Field(max_length=6)
