from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

OAuthProvider = Literal["qq", "xuexitong"]
AuthType = Literal["password", "oauth"]
UserRole = Literal["student", "admin"]
AdminBatchAction = Literal["activate", "deactivate", "delete", "set_role"]

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_PHONE_RE = re.compile(r"^1[3-9]\d[\s]?\d{4}[\s]?\d{4}$")
_IDENTIFIER_EXPLAIN = "请输入有效的邮箱或手机号（11 位中国大陆手机号）"


def _validate_identifier(value: str) -> str:
    trimmed = value.strip()
    if _EMAIL_RE.match(trimmed) or _PHONE_RE.match(trimmed):
        return trimmed
    raise ValueError(_IDENTIFIER_EXPLAIN)


def _validate_required_text(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("不能为空")
    return trimmed


def _validate_class_name_is_not_identifier(identifier: str, class_name: str) -> None:
    if identifier.strip() == class_name.strip():
        raise ValueError("班级不能填写登录标识")


# ── Auth ──


class LoginRequest(BaseModel):
    account: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("account")
    @classmethod
    def validate_account(cls, v: str) -> str:
        return _validate_identifier(v)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    identifier: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=6, max_length=128)
    confirm_password: str = Field(min_length=6, max_length=128)
    role: UserRole = "student"
    school: str = Field(min_length=1, max_length=128)
    major: str = Field(min_length=1, max_length=128)
    class_name: str = Field(min_length=1, max_length=128)

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, v: str) -> str:
        return _validate_identifier(v)

    @field_validator("username", "school", "major", "class_name")
    @classmethod
    def validate_required_text(cls, v: str) -> str:
        return _validate_required_text(v)

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, confirm_password: str, info: object) -> str:
        data = getattr(info, "data", {})
        if data.get("password") != confirm_password:
            raise ValueError("两次输入的密码不一致")
        return confirm_password

    @model_validator(mode="after")
    def class_name_must_not_equal_identifier(self) -> "RegisterRequest":
        _validate_class_name_is_not_identifier(self.identifier, self.class_name)
        return self


class OAuthRequest(BaseModel):
    provider: OAuthProvider
    authorization_code: str = Field(min_length=4, max_length=64)


class UserRead(BaseModel):
    uid: str
    username: str
    identifier: str
    role: UserRole
    school: str
    major: str
    class_name: str
    provider: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    auth_type: AuthType
    user: UserRead


class AdminAccountCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    identifier: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=6, max_length=128)
    role: UserRole
    is_active: bool = True
    school: str = Field(min_length=1, max_length=128)
    major: str = Field(min_length=1, max_length=128)
    class_name: str = Field(min_length=1, max_length=128)

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, v: str) -> str:
        return _validate_identifier(v)

    @field_validator("username", "school", "major", "class_name")
    @classmethod
    def validate_required_text(cls, v: str) -> str:
        return _validate_required_text(v)

    @model_validator(mode="after")
    def class_name_must_not_equal_identifier(self) -> "AdminAccountCreateRequest":
        _validate_class_name_is_not_identifier(self.identifier, self.class_name)
        return self


class AdminAccountUpdateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    identifier: str = Field(min_length=3, max_length=128)
    role: UserRole
    is_active: bool
    password: str | None = Field(default=None, min_length=6, max_length=128)
    school: str = Field(min_length=1, max_length=128)
    major: str = Field(min_length=1, max_length=128)
    class_name: str = Field(min_length=1, max_length=128)

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, v: str) -> str:
        return _validate_identifier(v)

    @field_validator("username", "school", "major", "class_name")
    @classmethod
    def validate_required_text(cls, v: str) -> str:
        return _validate_required_text(v)

    @model_validator(mode="after")
    def class_name_must_not_equal_identifier(self) -> "AdminAccountUpdateRequest":
        _validate_class_name_is_not_identifier(self.identifier, self.class_name)
        return self


class AdminAccountBatchRequest(BaseModel):
    action: AdminBatchAction
    uids: list[str] = Field(min_length=1)
    role: UserRole | None = None

    @model_validator(mode="after")
    def validate_role_for_action(self) -> "AdminAccountBatchRequest":
        if self.action == "set_role" and self.role is None:
            raise ValueError("批量修改角色时必须提供 role")
        return self


class AdminAccountImportRequest(BaseModel):
    csv_text: str = Field(min_length=1)


class AdminAccountImportFailure(BaseModel):
    row: int
    identifier: str | None = None
    reason: str


class AdminAccountImportResponse(BaseModel):
    created: int
    updated: int
    failed: int
    failures: list[AdminAccountImportFailure] = Field(default_factory=list)


class CultivationProgramRead(BaseModel):
    program_id: str
    teacher_uid: str
    teacher_name: str
    teacher_identifier: str
    school: str
    major: str
    class_name: str
    courses: list[dict] = Field(default_factory=list)
    published_at: datetime | None
    updated_at: datetime


class CultivationProgramSaveRequest(BaseModel):
    courses: list[dict] = Field(default_factory=list)
    school: str | None = Field(default=None, max_length=128)
    major: str | None = Field(default=None, max_length=128)
    class_name: str | None = Field(default=None, max_length=128)


class DataOverviewResponse(BaseModel):
    accounts: dict[str, int]
    cohorts: int
    programs: int
    learning_data: dict[str, int]


class DataCohortRead(BaseModel):
    school: str
    major: str
    class_name: str
    student_count: int
    admin_count: int
    has_program: bool
    program_teacher_name: str | None = None
    program_updated_at: datetime | None = None


class UserLearningDataRead(BaseModel):
    user: UserRead
    profile: dict | None = None
    year_learning_paths: list[dict] = Field(default_factory=list)
    course_outlines: list[dict] = Field(default_factory=list)
    chapter_quizzes: list[dict] = Field(default_factory=list)
    chapter_progress: list[dict] = Field(default_factory=list)
    chapter_weaknesses: list[dict] = Field(default_factory=list)
    resource_quality: list[dict] = Field(default_factory=list)
    conversation_sessions: list[dict] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok", "error"]
    database: Literal["connected", "unavailable"]


class LivenessResponse(BaseModel):
    status: Literal["ok"]


# ── Knowledge Base ──

KnowledgeSourceStatus = Literal["enabled", "disabled"]
KnowledgeSourceDownloadStatus = Literal["unverified", "verified", "failed"]
KnowledgeSourceParseStatus = Literal["unverified", "supported", "failed"]
KnowledgeSourceLicenseReviewStatus = Literal["unreviewed", "approved", "rejected"]
KnowledgeSourceHumanReviewStatus = Literal["unreviewed", "reviewed"]

TextbookIngestionStatus = Literal[
    "not_started",
    "processing",
    "failed",
    "ready_for_outline_review",
    "completed",
]
TextbookOutlineReviewStatus = Literal["unreviewed", "approved"]
TextbookStudentAvailabilityStatus = Literal[
    "draft",
    "published",
    "unpublished",
    "archived",
]

KnowledgeBaseIngestionJobStatus = Literal["queued", "running", "failed", "completed"]
KnowledgeGapStatus = Literal[
    "open",
    "material_searching",
    "material_found",
    "resolved",
    "closed",
]
KnowledgeGapNoticeType = Literal["knowledge_gap_resolved"]
KnowledgeGapNoticeAction = Literal["regenerate_learning_path_intake"]
TextbookExtensionResourceRenderMode = Literal["reader", "video", "webpage"]


class KnowledgeSourceStatusContract(BaseModel):
    status: KnowledgeSourceStatus
    download_status: KnowledgeSourceDownloadStatus
    parse_status: KnowledgeSourceParseStatus
    license_review_status: KnowledgeSourceLicenseReviewStatus
    human_review_status: KnowledgeSourceHumanReviewStatus


class TextbookStatusContract(BaseModel):
    ingestion_status: TextbookIngestionStatus
    outline_review_status: TextbookOutlineReviewStatus
    student_availability_status: TextbookStudentAvailabilityStatus


class KnowledgeBaseIngestionJobStatusContract(BaseModel):
    status: KnowledgeBaseIngestionJobStatus


class KnowledgeGapStatusContract(BaseModel):
    status: KnowledgeGapStatus


class KnowledgeGapNoticeActionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: KnowledgeGapNoticeAction
    learning_topic: str
    textbook_id: str


class KnowledgeGapNoticeStatusContract(BaseModel):
    notice_type: KnowledgeGapNoticeType
    action_payload: KnowledgeGapNoticeActionPayload


class TextbookExtensionResourceRenderModeContract(BaseModel):
    render_mode: TextbookExtensionResourceRenderMode


class KnowledgeSourceCreateRequest(BaseModel):
    source_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=256)
    base_url: str = Field(default="", max_length=1024)
    status: KnowledgeSourceStatus = "enabled"
    source_kind: str = Field(default="", max_length=64)
    download_requirement: str = ""
    ai_search_requirement: str = ""
    download_status: KnowledgeSourceDownloadStatus = "unverified"
    parse_status: KnowledgeSourceParseStatus = "unverified"
    license_review_status: KnowledgeSourceLicenseReviewStatus = "unreviewed"
    human_review_status: KnowledgeSourceHumanReviewStatus = "unreviewed"


class KnowledgeSourceRead(KnowledgeSourceCreateRequest):
    model_config = ConfigDict(from_attributes=True)


class TextbookCreateRequest(BaseModel):
    textbook_id: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=256)
    original_title: str = Field(default="", max_length=256)
    language: str = Field(default="", max_length=32)
    translated_language: str = Field(default="", max_length=32)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    download_url: str = Field(default="", max_length=1024)
    file_asset_url: str = Field(default="", max_length=1024)
    outline: dict[str, object] = Field(default_factory=dict)
    ingestion_status: TextbookIngestionStatus = "not_started"
    outline_review_status: TextbookOutlineReviewStatus = "unreviewed"
    student_availability_status: TextbookStudentAvailabilityStatus = "draft"
    ingestion_error_message: str = ""


class TextbookRead(TextbookCreateRequest):
    model_config = ConfigDict(from_attributes=True)

    published_at: datetime | None = None
    unpublished_at: datetime | None = None
    archived_at: datetime | None = None


class TextbookSectionContentCreateRequest(BaseModel):
    section_content_id: str = Field(min_length=1, max_length=64)
    section_id: str = Field(min_length=1, max_length=128)
    parent_section_id: str | None = Field(default=None, max_length=128)
    order_index: int = 0
    title: str = Field(min_length=1, max_length=256)
    original_title: str = Field(default="", max_length=256)
    content_original: str = ""
    content_zh: str = ""
    content_char_count: int = 0


class TextbookSectionContentRead(TextbookSectionContentCreateRequest):
    model_config = ConfigDict(from_attributes=True)

    textbook_id: str


class StructuredTextbookCreateRequest(BaseModel):
    textbook: TextbookCreateRequest
    sections: list[TextbookSectionContentCreateRequest]


class KnowledgeBaseIngestionJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    textbook_id: str
    job_type: str
    status: KnowledgeBaseIngestionJobStatus
    error_message: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class KnowledgeGapRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    gap_id: str
    normalized_topic: str
    trigger_count: int
    follow_count: int
    latest_triggered_at: datetime | None
    student_goal_summaries: list[str]
    status: KnowledgeGapStatus
    resolved_textbook_id: str | None
    resolved_at: datetime | None


class KnowledgeGapAdminRead(KnowledgeGapRead):
    sources: list[KnowledgeSourceRead] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)


class KnowledgeGapFindMaterialsResponse(BaseModel):
    gap: KnowledgeGapRead
    sources: list[KnowledgeSourceRead]


class KnowledgeGapUploadResponse(BaseModel):
    gap: KnowledgeGapRead
    textbook: TextbookRead


class KnowledgeBaseSourceResult(BaseModel):
    source_result_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=256)
    original_title: str = Field(default="", max_length=256)
    language: str = Field(default="", max_length=32)
    source_url: str = Field(min_length=1, max_length=1024)
    source_type: Literal["pdf", "html"]
    provider_name: str = Field(default="", max_length=256)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    parseability_score: int = Field(ge=0, le=100)
    parseability_reason: str = ""
    topic_summary: str = ""
    is_recommended: bool = False
    already_imported: bool = False
    textbook_id: str | None = None


class KnowledgeBaseSourceConfirmRequest(BaseModel):
    source_result: KnowledgeBaseSourceResult


class KnowledgeBaseSourceConfirmResponse(BaseModel):
    textbook: TextbookRead
    job: KnowledgeBaseIngestionJobRead


class KnowledgeBaseAgentTextbookHit(BaseModel):
    textbook_id: str
    title: str
    source_name: str
    student_availability_status: TextbookStudentAvailabilityStatus
    score: int = Field(ge=0)
    reason: str = ""


class KnowledgeBaseAgentGapHit(BaseModel):
    gap_id: str
    normalized_topic: str
    status: KnowledgeGapStatus
    reason: str = ""


class KnowledgeBaseAgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class KnowledgeBaseAgentResponse(BaseModel):
    reply_text: str
    selected_textbook_id: str | None = None
    selected_source_result_id: str | None = None
    textbook_hits: list[KnowledgeBaseAgentTextbookHit] = Field(default_factory=list)
    gap_hits: list[KnowledgeBaseAgentGapHit] = Field(default_factory=list)
    source_results: list[KnowledgeBaseSourceResult] = Field(default_factory=list)


class KnowledgeGapFollowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    follow_id: str
    gap_id: str
    user_uid: str
    created_at: datetime


class KnowledgeGapNoticeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notice_id: str
    gap_id: str
    user_uid: str
    notice_type: KnowledgeGapNoticeType
    title: str
    body: str
    action_label: str
    action_payload: KnowledgeGapNoticeActionPayload
    read_at: datetime | None
    created_at: datetime


class TextbookExtensionResourceCreateRequest(BaseModel):
    resource_id: str = Field(min_length=1, max_length=64)
    section_id: str = Field(min_length=1, max_length=128)
    resource_type: str = Field(default="", max_length=64)
    title_zh: str = Field(min_length=1, max_length=256)
    description_zh: str = ""
    render_mode: TextbookExtensionResourceRenderMode = "reader"
    url: str = Field(default="", max_length=1024)
    cover_url: str = Field(default="", max_length=1024)
    source_name: str = Field(default="", max_length=256)
    status: str = Field(default="", max_length=32)


class TextbookExtensionResourceRead(TextbookExtensionResourceCreateRequest):
    model_config = ConfigDict(from_attributes=True)

    textbook_id: str


# ── Chat ──


class ChatStartRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)


class ChatMessageRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=4000)
    image_attachment: str | None = Field(
        default=None, description="Base64 encoded image attachment"
    )


class ChatResponse(BaseModel):
    session_id: str
    reply_text: str | None = None
    profile: dict | None = None
    year_learning_paths: dict | None = None
    course_knowledge: dict | None = None


class SessionStateResponse(BaseModel):
    session_id: str
    user_uid: str
    messages: list[dict] = Field(default_factory=list)
    profile: dict | None = None
    year_learning_paths: dict | None = None
    latest_grade_year: str | None = None
    course_knowledge: dict | None = None
    updated_at: datetime


# ── Learning Path ──


class YearLearningPathsReadResponse(BaseModel):
    year_learning_paths: dict[str, dict]
    updated_at: datetime | None = None


BranchCourseStatus = Literal["completed", "current", "locked"]


class BranchCourseNodeRead(BaseModel):
    course_node_id: str
    course_or_chapter_theme: str
    course_goal: str
    status: BranchCourseStatus
    has_outline: bool


class BranchYearRead(BaseModel):
    grade_id: str
    grade_name: str
    has_courses: bool
    has_outline_content: bool
    is_clickable: bool
    current_course_id: str | None = None
    courses: list[BranchCourseNodeRead]


class BranchOverviewReadResponse(BaseModel):
    years: dict[str, BranchYearRead]
    updated_at: datetime | None = None


class CanopyCourseNode(BaseModel):
    id: str
    title: str
    grade: str
    status: str
    score: int | None = None
    description: str
    prerequisite_ids: list[str] = Field(default_factory=list)


class CanopyMilestone(BaseModel):
    date: str
    title: str
    desc: str
    reached: bool


class CourseQualityScore(BaseModel):
    accuracy: int = Field(default=0, ge=0, le=100)
    difficulty_fit: int = Field(default=0, ge=0, le=100)
    completeness: int = Field(default=0, ge=0, le=100)
    overall: int = Field(default=0, ge=0, le=100)
    suggestions: list[str] = Field(default_factory=list)
    scored_at: str | None = None


class CanopyOverviewResponse(BaseModel):
    courses: list[CanopyCourseNode] = Field(default_factory=list)
    growth_stage: int
    completed_count: int
    active_rate: int
    avg_score: int
    focused_hours: float
    milestones: list[CanopyMilestone] = Field(default_factory=list)
    quality_scores: dict[str, CourseQualityScore] = Field(default_factory=dict)


LeafAccessState = Literal["available", "locked"]


class LeafCourseRead(BaseModel):
    course_node_id: str
    grade_id: str
    course_or_chapter_theme: str
    course_goal: str
    status: BranchCourseStatus
    has_outline: bool


class LeafGenerationStatusRead(BaseModel):
    course_node_id: str
    chapter_section_id: str
    status: Literal["running"]
    message: str


class LeafCourseReadResponse(BaseModel):
    access_state: LeafAccessState
    course: LeafCourseRead
    outline: dict | None = None
    sections: list[dict] = Field(default_factory=list)
    section_composed_markdowns: dict[str, dict] = Field(default_factory=dict)
    section_resource_errors: dict[str, dict] = Field(default_factory=dict)
    generation_status: LeafGenerationStatusRead | None = None
    can_generate: bool
    first_generatable_chapter_id: str | None = None
    locked_reason: str | None = None


ForestQuestionType = Literal["single_choice", "code", "image_upload"]
ForestProgressState = Literal["locked", "available", "passed"]
ForestQuizStatus = Literal["generating", "ready", "error"]


class ForestQuizQuestionRead(BaseModel):
    question_id: str
    type: ForestQuestionType
    prompt: str
    options: list[dict] = Field(default_factory=list)
    starter_code: str = ""
    image_prompt: str = ""
    points: int = 0


class ForestQuizRead(BaseModel):
    quiz_id: str
    course_node_id: str
    chapter_id: str
    status: ForestQuizStatus
    questions: list[ForestQuizQuestionRead] = Field(default_factory=list)
    generation_error: str = ""
    created_at: datetime
    updated_at: datetime


class ForestAttemptRead(BaseModel):
    attempt_id: str
    quiz_id: str
    score: int
    passed: bool
    answers: dict
    grading_result: dict
    created_at: datetime


class ForestChapterProgressRead(BaseModel):
    course_node_id: str
    chapter_id: str
    state: ForestProgressState
    best_score: int
    latest_attempt_id: str | None = None
    passed_at: datetime | None = None
    updated_at: datetime


class ForestQuizSessionReadResponse(BaseModel):
    course: LeafCourseRead
    chapter: dict
    quiz: ForestQuizRead | None = None
    latest_attempt: ForestAttemptRead | None = None
    progress: ForestChapterProgressRead
    next_unlocked_chapter_id: str | None = None
    next_course_id: str | None = None


class ForestQuizGenerateRequest(BaseModel):
    regenerate: bool = False


class ForestQuizAttemptCreateRequest(BaseModel):
    answers: dict


class ForestAiContext(BaseModel):
    course_node_id: str
    chapter_id: str
    quiz_id: str | None = None
    question_id: str | None = None
    question: dict | None = None
    answer: object | None = None
    grading_result: dict | None = None


class ForestAiStreamRequest(BaseModel):
    course_node_id: str
    chapter_id: str
    quiz_id: str | None = None
    question_id: str | None = None
    message: str = Field(min_length=1, max_length=4000)
    active_question_context: ForestAiContext
    image_attachment: str | None = Field(
        default=None, description="Base64 encoded image attachment"
    )
