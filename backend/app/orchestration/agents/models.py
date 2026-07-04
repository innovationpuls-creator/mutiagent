"""Pydantic models used by orchestration agents and local validation.

Some agents use structured LLM output. Course outline generation parses JSON
text and validates locally because the current production model does not
support structured output.
"""

from __future__ import annotations

import json
import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ── Profile Agent ────────────────────────────────────────────────────────

ChatStage = Literal[
    "basic_info", "learning_preference", "ability_basis", "goal_constraint", "generated"
]
QuestionMode = Literal["question_md", "question_box", "none"]
GradeId = Literal["year_1", "year_2", "year_3", "year_4"]
SemesterScope = Literal["上学期", "下学期", "寒假", "暑假", "全年级内弹性安排"]
HierarchyLevel = Literal["课程", "章节", "主题", "知识点"]
KnowledgePointLevel = Literal["基础", "核心", "进阶", "应用"]
RelationType = Literal[
    "prerequisite",
    "contains",
    "parallel",
    "reinforces",
    "applies_to",
    "extends",
    "review_before",
    "resource_basis_for",
]
ResourceAgent = Literal[
    "learning_resource_agent",
    "question_bank_agent",
    "document_agent",
    "code_example_agent",
    "video_script_agent",
    "dynamic_update_agent",
]
ResourceType = Literal[
    "学习资源", "题库", "文档", "代码示例", "视频脚本", "动态更新任务"
]
DifficultyLevel = Literal["入门", "基础", "中级", "高级"]
GoalType = Literal["考试", "课程学习", "项目实践", "能力提升", "就业准备", "其他"]
REQUIRED_GRADE_PLAN_KEYS = frozenset({"year_1", "year_2", "year_3", "year_4"})
MAX_SOURCE_SECTION_COUNT = 7
_PROFILE_STRING_FIELDS = (
    "current_grade",
    "major",
    "learning_stage",
    "has_clear_goal",
    "learning_method_preference",
    "learning_pace_preference",
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


class ConfirmedInfoOutput(BaseModel):
    """SessionMessage confirmed_info 结构。"""

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

    @field_validator("content_preference", mode="before")
    @classmethod
    def normalize_content_preference(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        return value

    @field_validator(*_PROFILE_STRING_FIELDS, mode="before")
    @classmethod
    def normalize_profile_text_field(cls, value: object) -> object:
        if isinstance(value, (list, tuple, set)):
            normalized = [str(item).strip() for item in value if str(item).strip()]
            return "、".join(normalized)
        return value


class QuestionBoxOptionOutput(BaseModel):
    """SessionMessage question_box.options 单项。"""

    label: str = Field(description="选项展示文本")
    value: str = Field(description="选项值")
    description: str = Field(default="", description="选项说明")
    target_fields: list[str] = Field(
        default_factory=list, description="该选项影响的字段"
    )
    fills: dict[str, str | list[str]] = Field(
        default_factory=dict, description="该选项填充的字段值"
    )


class QuestionBoxOutput(BaseModel):
    """SessionMessage question_box 结构。"""

    question: str = Field(description="问题文本")
    options: list[QuestionBoxOptionOutput] = Field(description="可选答案")


class QuestionFormQuestionOutput(BaseModel):
    """表单问题定义。"""

    field_name: str = Field(description="ConfirmedInfo 中的字段名")
    label: str = Field(description="字段展示标签")
    description: str = Field(default="", description="字段说明")
    input_type: Literal["single_choice", "multi_choice", "free_text"] = Field(
        description="输入类型"
    )
    required: bool = Field(default=True, description="是否必填")
    options: list[QuestionBoxOptionOutput] = Field(
        default_factory=list, description="选项列表"
    )


class QuestionFormOutput(BaseModel):
    """动态表单结构。"""

    title: str = Field(description="表单标题")
    description: str = Field(description="表单说明")
    stage: ChatStage = Field(description="所属画像阶段")
    questions: list[QuestionFormQuestionOutput] = Field(description="问题列表")
    submit_label: str = Field(default="提交", description="提交按钮文本")


class ProfileSessionOutput(BaseModel):
    """画像 Agent 的 SessionMessage 兼容结构化输出。"""

    type: Literal["collecting", "basic_profile"] = Field(description="消息类型")
    stage: ChatStage = Field(description="当前画像阶段")
    question_mode: QuestionMode = Field(description="提问模式")
    confirmed_info: ConfirmedInfoOutput = Field(description="已确认画像信息")
    defaulted_fields: list[str] = Field(description="由系统补全的字段")
    question_md: str = Field(description="Markdown 问题文本")
    question_box: QuestionBoxOutput = Field(description="结构化问题框")
    question_form: QuestionFormOutput | None = Field(
        default=None, description="动态表单"
    )
    text: str = Field(description="自然语言回复文本")


# ── Learning Path Agent ──────────────────────────────────────────────────


class LearningPathIntakeCourseOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="课程名称")
    purpose: str = Field(description="课程安排目的")
    source_textbook_id: str = Field(description="绑定教材 ID")
    source_textbook_title: str = Field(description="绑定教材标题")
    source_outline_section_ids: list[str] = Field(
        min_length=1,
        max_length=MAX_SOURCE_SECTION_COUNT,
        description="绑定教材目录小节 ID",
    )

    @field_validator("title", "purpose", "source_textbook_id", "source_textbook_title")
    @classmethod
    def require_text(cls, value: str, info) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError(f"{info.field_name} must not be empty")
        return text

    @field_validator("source_outline_section_ids")
    @classmethod
    def require_source_outline_section_ids(cls, value: list[str]) -> list[str]:
        return _require_text_list(value, "source_outline_section_ids")


class LearningPathIntakeOutput(BaseModel):
    type: Literal["learning_path_intake"] = Field(default="learning_path_intake")
    status: Literal["draft", "confirmed", "risk_pending"] = Field(
        description="课程草案状态"
    )
    grade_year: GradeId = Field(description="目标年级 ID")
    grade_name: str = Field(description="目标年级名称")
    learning_topic: str = Field(description="学习方向")
    courses: list[LearningPathIntakeCourseOutput] = Field(min_length=4, max_length=8)
    recommendation_reasons: list[str] = Field(min_length=1, description="简短推荐依据")
    user_modification_summary: str = Field(default="")
    risk_warnings: list[str] = Field(default_factory=list)
    requires_second_confirmation: bool = Field(default=False)

    @field_validator("grade_name", "learning_topic")
    @classmethod
    def require_text(cls, value: str, info) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError(f"{info.field_name} must not be empty")
        return text

    @field_validator("recommendation_reasons", "risk_warnings", mode="before")
    @classmethod
    def normalize_text_list(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        return value


class LearningPathIntakeDraftCourseLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="课程名称")
    purpose: str = Field(description="课程安排目的")
    source_textbook_id: str = Field(description="绑定教材 ID")
    source_textbook_title: str = Field(description="绑定教材标题")
    source_outline_section_ids: list[str] = Field(
        min_length=1,
        description="绑定教材目录小节 ID",
    )

    @field_validator("title", "purpose", "source_textbook_id", "source_textbook_title")
    @classmethod
    def require_text(cls, value: str, info) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError(f"{info.field_name} must not be empty")
        return text

    @field_validator("source_outline_section_ids")
    @classmethod
    def require_source_outline_section_ids(cls, value: list[str]) -> list[str]:
        return _require_text_list(value, "source_outline_section_ids")


class LearningPathIntakeDraftLLMOutput(BaseModel):
    type: Literal["learning_path_intake"] = Field(default="learning_path_intake")
    status: Literal["draft", "confirmed", "risk_pending"] = Field(
        description="课程草案状态"
    )
    grade_year: str = Field(description="目标年级 ID 或用户自然年级表达")
    grade_name: str = Field(description="目标年级名称")
    learning_topic: str = Field(description="学习方向")
    courses: list[LearningPathIntakeDraftCourseLLMOutput] = Field(
        min_length=4, max_length=8
    )
    recommendation_reasons: list[str] = Field(min_length=1, description="简短推荐依据")
    user_modification_summary: str = Field(default="")
    risk_warnings: list[str] = Field(default_factory=list)
    requires_second_confirmation: bool = Field(default=False)

    @field_validator("grade_year", mode="before")
    @classmethod
    def normalize_grade_year_input(cls, value: object) -> object:
        if isinstance(value, int):
            return str(value)
        return value

    @field_validator("grade_year", "grade_name", "learning_topic")
    @classmethod
    def require_text(cls, value: str, info) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError(f"{info.field_name} must not be empty")
        return text

    @field_validator("recommendation_reasons", "risk_warnings", mode="before")
    @classmethod
    def normalize_text_list(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        return value


class LearningPathIntakeDraftOutput(BaseModel):
    type: Literal["learning_path_intake"] = Field(default="learning_path_intake")
    status: Literal["draft", "confirmed", "risk_pending"] = Field(
        description="课程草案状态"
    )
    grade_year: str = Field(description="目标年级 ID 或用户自然年级表达")
    grade_name: str = Field(description="目标年级名称")
    learning_topic: str = Field(description="学习方向")
    courses: list[LearningPathIntakeCourseOutput] = Field(min_length=4, max_length=8)
    recommendation_reasons: list[str] = Field(min_length=1, description="简短推荐依据")
    user_modification_summary: str = Field(default="")
    risk_warnings: list[str] = Field(default_factory=list)
    requires_second_confirmation: bool = Field(default=False)

    @field_validator("grade_year", mode="before")
    @classmethod
    def normalize_grade_year_input(cls, value: object) -> object:
        if isinstance(value, int):
            return str(value)
        return value

    @field_validator("grade_year", "grade_name", "learning_topic")
    @classmethod
    def require_text(cls, value: str, info) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError(f"{info.field_name} must not be empty")
        return text

    @field_validator("recommendation_reasons", "risk_warnings", mode="before")
    @classmethod
    def normalize_text_list(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        return value


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


class LearningPathCourseSpecOutput(BaseModel):
    """学习路径规划骨架中的单门课程定义。"""

    theme: str = Field(default="", min_length=1, description="课程主题")
    semester_scope: str = Field(
        default="第1-16周", min_length=1, description="建议安排学期或阶段时间说明"
    )
    duration: str = Field(default="16周", min_length=1, description="持续时间")
    pace_reason: str = Field(
        default="按课程标准节奏安排", min_length=1, description="这样安排节奏的原因"
    )
    goal: str = Field(default="", min_length=1, description="课程目标")
    stage_titles: list[str] = Field(
        default=[], min_length=3, description="阶段标题，按学习顺序排列"
    )
    key_points: list[str] = Field(
        default=[], min_length=3, description="课程核心知识点"
    )
    difficult_points: list[str] = Field(
        default=[], min_length=1, description="课程难点"
    )
    acceptance_criteria: list[str] = Field(
        default=[], min_length=1, description="课程验收标准"
    )
    difficulty_level: str = Field(
        default="中级", min_length=1, description="课程难度等级"
    )

    @field_validator(
        "stage_titles",
        "key_points",
        "difficult_points",
        "acceptance_criteria",
        mode="before",
    )
    @classmethod
    def normalize_course_spec_text_list(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []

            normalized = re.sub(r"[•●▪◦]", "\n", text)
            normalized = re.sub(r"\d+[.)、]\s*", "\n", normalized)
            line_parts = [
                part.strip(" \t-")
                for part in re.split(r"[\r\n;；|]+", normalized)
                if part.strip(" \t-")
            ]
            if len(line_parts) > 1:
                return line_parts

            comma_parts = [
                part.strip() for part in re.split(r"[，,、]", text) if part.strip()
            ]
            if len(comma_parts) > 1:
                return comma_parts

            return [text]
        if isinstance(value, (tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return value


class LearningPathPlanOutput(BaseModel):
    """学习路径轻量规划输出，后端再展开为完整契约。"""

    goal_type: str = Field(default="", min_length=1, description="目标类型")
    grade_goal: str = Field(default="", min_length=1, description="当前学年的阶段目标")
    desired_outcome: str = Field(
        default="", min_length=1, description="当前学年希望达成的结果"
    )
    four_year_outcome: str = Field(
        default="", min_length=1, description="四年阶段最终结果"
    )
    current_focus: str = Field(
        default="", min_length=1, description="当前最应该先聚焦的事情"
    )
    next_action: str = Field(
        default="", min_length=1, description="当前最具体的下一步动作"
    )
    course_specs: list[LearningPathCourseSpecOutput] = Field(
        min_length=4, max_length=8, description="按先后顺序排列的课程"
    )


class TimeArrangementOutput(BaseModel):
    """课程节点时间安排。"""

    semester_scope: SemesterScope = Field(description="学期范围")
    duration: str = Field(description="持续时间")
    pace_reason: str = Field(description="节奏安排理由")


class KnowledgePointOutput(BaseModel):
    """知识点节点。"""

    knowledge_point_id: str = Field(description="知识点 ID")
    name: str = Field(description="知识点名称")
    parent_knowledge_point_id: str | None = Field(description="父知识点 ID")
    level: KnowledgePointLevel = Field(description="知识点层级")
    description: str = Field(description="知识点说明")
    mastery_standard: str = Field(description="掌握标准")


class KnowledgeHierarchyOutput(BaseModel):
    """章节内知识层级。"""

    hierarchy_id: str = Field(description="层级 ID")
    parent_hierarchy_id: str | None = Field(description="父层级 ID")
    hierarchy_level: HierarchyLevel = Field(description="层级类型")
    title: str = Field(description="层级标题")
    summary: str = Field(description="层级摘要")
    knowledge_point_ids: list[str] = Field(description="关联知识点 ID")


class KnowledgeRelationOutput(BaseModel):
    """知识节点关系。"""

    from_node_id: str = Field(description="起点节点 ID")
    to_node_id: str = Field(description="终点节点 ID")
    relation_type: RelationType = Field(description="关系类型")
    description: str = Field(description="关系说明")


class ChapterNodeOutput(BaseModel):
    """课程章节节点。"""

    chapter_node_id: str = Field(description="章节节点 ID")
    chapter_theme: str = Field(description="章节主题")
    knowledge_hierarchy: list[KnowledgeHierarchyOutput] = Field(description="知识层级")
    core_knowledge_point_ids: list[str] = Field(description="核心知识点 ID")
    key_points: list[str] = Field(description="重点")
    difficult_points: list[str] = Field(description="难点")
    prerequisite_node_ids: list[str] = Field(description="前置节点 ID")
    learning_sequence: list[str] = Field(description="学习顺序")
    knowledge_relations: list[KnowledgeRelationOutput] = Field(description="知识关系")
    downstream_resource_direction_ids: list[str] = Field(description="后续资源方向 ID")


class CourseNodeOutput(BaseModel):
    """课程节点。"""

    model_config = ConfigDict(extra="forbid")

    course_node_id: str = Field(description="课程节点 ID")
    grade_id: GradeId = Field(description="所属年级 ID")
    course_or_chapter_theme: str = Field(description="课程或章节主题")
    source_textbook_id: str = Field(description="绑定教材 ID")
    source_textbook_title: str = Field(description="绑定教材标题")
    source_outline_section_ids: list[str] = Field(
        min_length=1,
        max_length=MAX_SOURCE_SECTION_COUNT,
        description="绑定教材目录小节 ID",
    )
    course_stage_plan: list[str] = Field(
        min_length=1, description="课程阶段计划，按学习顺序排列"
    )
    time_arrangement: TimeArrangementOutput = Field(description="时间安排")
    course_goal: str = Field(description="课程目标")
    prerequisite_node_ids: list[str] = Field(description="前置节点 ID")
    chapter_nodes: list[ChapterNodeOutput] = Field(description="章节节点")
    core_knowledge_points: list[KnowledgePointOutput] = Field(description="核心知识点")
    key_points: list[str] = Field(description="重点")
    difficult_points: list[str] = Field(description="难点")
    learning_sequence: list[str] = Field(description="学习顺序")
    knowledge_relations: list[KnowledgeRelationOutput] = Field(description="知识关系")
    downstream_resource_direction_ids: list[str] = Field(description="后续资源方向 ID")
    acceptance_criteria: list[str] = Field(description="验收标准")

    @field_validator(
        "course_node_id",
        "course_or_chapter_theme",
        "source_textbook_id",
        "source_textbook_title",
        "course_goal",
    )
    @classmethod
    def require_text(cls, value: str, info) -> str:
        return _required_text(value, info.field_name)

    @field_validator("source_outline_section_ids", "course_stage_plan")
    @classmethod
    def require_text_list(cls, value: list[str], info) -> list[str]:
        return _require_text_list(value, info.field_name)


class GradePlanOutput(BaseModel):
    """年级课程计划。"""

    grade_id: GradeId = Field(description="年级 ID")
    grade_name: str = Field(description="年级名称")
    grade_goal: str = Field(description="年级目标")
    course_nodes: list[CourseNodeOutput] = Field(description="课程节点")


class CriticalPathOutput(BaseModel):
    """关键路径。"""

    path_id: str = Field(description="路径 ID")
    purpose: str = Field(description="路径目的")
    ordered_node_ids: list[str] = Field(description="有序节点 ID")


class ResourceDirectionOutput(BaseModel):
    """资源生成方向。"""

    resource_direction_id: str = Field(description="资源方向 ID")
    target_node_ids: list[str] = Field(description="目标节点 ID")
    resource_type: ResourceType = Field(description="资源类型")
    generation_goal: str = Field(description="生成目标")
    content_requirements: list[str] = Field(description="内容要求")
    difficulty_level: DifficultyLevel = Field(description="难度等级")


class LearningGoalOutput(BaseModel):
    """学习目标。"""

    target_course_or_skill: str = Field(description="目标课程或能力")
    goal_type: GoalType = Field(description="目标类型")
    desired_outcome: str = Field(description="期望结果")
    four_year_outcome: str = Field(description="四年结果")


class LearnerBaselineOutput(BaseModel):
    """学习者基线。"""

    current_grade: str = Field(description="当前年级")
    major: str = Field(description="专业")
    mastered_content: list[str] = Field(description="已掌握内容")
    weaknesses: list[str] = Field(description="薄弱项")
    constraints: list[str] = Field(description="约束")
    weekly_available_time: str = Field(description="每周可投入时间")


class PlanningRulesOutput(BaseModel):
    """学习路径规划规则。"""

    node_unit: Literal["course_node"] = Field(description="节点单位")
    grade_boundary_rule: str = Field(description="年级边界规则")
    sequence_rule: str = Field(description="顺序规则")
    resource_rule: str = Field(description="资源规则")


class KnowledgeGraphOutput(BaseModel):
    """学习路径知识图谱。"""

    global_relations: list[KnowledgeRelationOutput] = Field(description="全局关系")
    critical_paths: list[CriticalPathOutput] = Field(description="关键路径")


class ResourceGenerationContractOutput(BaseModel):
    """资源生成契约。"""

    downstream_agents: list[ResourceAgent] = Field(description="下游 Agent")
    resource_directions: list[ResourceDirectionOutput] = Field(description="资源方向")


class DynamicUpdateContractOutput(BaseModel):
    """动态更新契约。"""

    trackable_metrics: list[str] = Field(description="可追踪指标")
    update_triggers: list[str] = Field(description="更新触发条件")
    adjustment_strategy: str = Field(description="调整策略")


class CurrentLearningCourse(BaseModel):
    """当前正在学习的课程节点摘要。"""

    grade_id: GradeId = Field(description="所属年级 ID")
    course_node_id: str = Field(description="课程节点 ID")
    course_or_chapter_theme: str = Field(description="课程或章节主题")
    course_goal: str = Field(description="课程目标")
    time_arrangement: TimeArrangementOutput = Field(description="时间安排")
    current_focus: str = Field(description="当前学习焦点")
    progress_state: Literal["in_progress", "completed"] = Field(description="进度状态")
    next_action: str = Field(description="下一步行动")


class LearningPathResultOutput(BaseModel):
    """learning_path.v2.course_node 学习路径输出。"""

    schema_version: Literal["learning_path.v2.course_node"] = Field(
        description="学习路径契约版本"
    )
    learning_goal: LearningGoalOutput = Field(description="学习目标")
    learner_baseline: LearnerBaselineOutput = Field(description="学习者基线")
    planning_rules: PlanningRulesOutput = Field(description="规划规则")
    grade_plans: dict[GradeId, GradePlanOutput] = Field(description="年级计划")
    knowledge_graph: KnowledgeGraphOutput = Field(description="知识图谱")
    resource_generation_contract: ResourceGenerationContractOutput = Field(
        description="资源生成契约"
    )
    dynamic_update_contract: DynamicUpdateContractOutput = Field(
        description="动态更新契约"
    )
    current_learning_courses: list[CurrentLearningCourse] = Field(
        default_factory=list, description="当前学习课程列表"
    )
    current_learning_course: CurrentLearningCourse = Field(description="当前学习课程")

    @model_validator(mode="after")
    def normalize_current_learning_courses(self) -> "LearningPathResultOutput":
        current_courses = list(self.current_learning_courses)
        if not current_courses:
            current_courses = [self.current_learning_course]

        first_course = current_courses[0]
        if first_course.progress_state not in {"in_progress", "completed"}:
            raise ValueError(
                "current_learning_course.progress_state must be in_progress "
                "or completed"
            )
        if self.current_learning_course != first_course:
            self.current_learning_course = first_course
        self.current_learning_courses = current_courses
        return self


ProfileOutput = ProfileSessionOutput
YearLearningPathOutput = LearningPathResultOutput


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

_RESOURCE_PLACEHOLDER_PATTERN = re.compile(
    r"<!--\s*(?P<kind>video|animation):id=(?P<id>[A-Za-z0-9_.:-]+)\s*-->"
)
_DISALLOWED_HTML_COLOR_PATTERN = re.compile(
    r"(#[0-9A-Fa-f]{3,8}\b|\brgba?\s*\(|\bhsla?\s*\()"
)
_SECTION_MARKDOWN_REQUIRED_HEADINGS = (
    "学习目标",
    "核心概念",
    "步骤讲解",
    "练习任务",
    "检查标准",
)
_SECTION_MARKDOWN_LOW_QUALITY_MARKERS = (
    "Key Concept",
    "This section explores foundational concepts",
    "视频资源暂时不可用",
    "动画暂时不可用",
    "Lesson Quiz",
    "Question 1 of 3",
)


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


def _placeholder_ids(markdown: str, kind: str) -> set[str]:
    return {
        match.group("id")
        for match in _RESOURCE_PLACEHOLDER_PATTERN.finditer(markdown)
        if match.group("kind") == kind
    }


def _has_markdown_heading(markdown: str, heading: str) -> bool:
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    return bool(re.search(pattern, markdown, re.MULTILINE))


def _markdown_heading_body(markdown: str, heading: str) -> str:
    heading_pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$")
    next_heading_pattern = re.compile(r"^##\s+\S")
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if not heading_pattern.match(line):
            continue
        body_lines = []
        for body_line in lines[index + 1 :]:
            if next_heading_pattern.match(body_line):
                break
            body_lines.append(body_line)
        return "\n".join(body_lines).strip()
    return ""


def _has_unique_terminal_markdown_level_two_heading(
    markdown: str, heading: str
) -> bool:
    heading_pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$")
    level_two_heading_pattern = re.compile(r"^##\s+\S")
    level_two_headings = [
        line for line in markdown.splitlines() if level_two_heading_pattern.match(line)
    ]
    matching_headings = [
        line for line in level_two_headings if heading_pattern.match(line)
    ]
    return (
        len(matching_headings) == 1
        and bool(level_two_headings)
        and bool(heading_pattern.match(level_two_headings[-1]))
    )


class SectionSourceReferenceOutput(BaseModel):
    textbook_id: str = Field(description="教材 ID")
    textbook_title: str = Field(description="教材标题")
    section_id: str = Field(description="教材小节 ID")
    section_title: str = Field(description="教材小节标题")
    evidence_summary: str = Field(description="教材依据摘要")
    content_char_count: int = Field(ge=0, description="教材正文字符数")

    @field_validator(
        "textbook_id",
        "textbook_title",
        "section_id",
        "section_title",
        "evidence_summary",
    )
    @classmethod
    def require_text_field(cls, value: str, info) -> str:
        return _required_text(value, info.field_name)


class AnimationVisualEntityOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(description="视觉对象 ID")
    kind: str = Field(description="视觉对象类型")

    @field_validator("id", "kind")
    @classmethod
    def require_text_field(cls, value: str, info) -> str:
        return _required_text(value, info.field_name)


class AnimationVisualRelationOutput(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    from_: str = Field(alias="from", description="关系起点")
    to: str = Field(description="关系终点")
    kind: str = Field(description="关系类型")

    @field_validator("from_", "to", "kind")
    @classmethod
    def require_text_field(cls, value: str, info) -> str:
        return _required_text(value, info.field_name)


class AnimationVisualModelOutput(BaseModel):
    entities: list[AnimationVisualEntityOutput] = Field(min_length=1)
    relations: list[AnimationVisualRelationOutput] = Field(default_factory=list)


class AnimationTimelineStepOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    step: int = Field(ge=1)
    action: str = Field(description="动作类型")
    target: str = Field(default="", description="动作目标")

    @field_validator("action")
    @classmethod
    def require_action(cls, value: str) -> str:
        return _required_text(value, "action")


class SectionAnimationBriefOutput(BaseModel):
    animation_id: str = Field(description="动画 ID")
    title: str = Field(description="动画标题")
    target_markdown_heading: str = Field(
        default="", description="服务的 Markdown 二级标题"
    )
    target_paragraph_summary: str = Field(default="", description="服务的正文段落摘要")
    concept: str = Field(description="需要动画解释的概念")
    simulation_type: str = Field(default="", description="模拟类型")
    visual_elements: list[str] = Field(
        default_factory=list, description="动画中必须出现的视觉元素"
    )
    visual_model: AnimationVisualModelOutput | None = None
    timeline: list[AnimationTimelineStepOutput] = Field(default_factory=list)
    layout: str = Field(default="", description="布局要求")
    motion: str = Field(
        default="", description="动画如何运动，包含节奏、方向与状态变化"
    )
    interaction: str = Field(default="", description="交互要求")
    success_check: list[str] = Field(default_factory=list, description="成功检查")
    space: str = Field(default="", description="动画空间尺寸或页面占位要求")
    placement_hint: str = Field(default="", description="建议插入位置")

    @field_validator("visual_elements", mode="before")
    @classmethod
    def normalize_visual_elements(cls, value: object) -> object:  # noqa: C901
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        if isinstance(value, list):
            normalized: list[str] = []
            for item in value:
                if isinstance(item, str):
                    text = item.strip()
                    if text:
                        normalized.append(text)
                    continue
                if isinstance(item, dict):
                    element = str(item.get("element", "")).strip()
                    content = str(item.get("content", "")).strip()
                    if element and content:
                        normalized.append(f"{element}：{content}")
                    elif element:
                        normalized.append(element)
                    elif content:
                        normalized.append(content)
                    else:
                        normalized.append(json.dumps(item, ensure_ascii=False))
                    continue
                text = str(item).strip()
                if text:
                    normalized.append(text)
            return normalized
        return value

    @field_validator(
        "target_markdown_heading",
        "target_paragraph_summary",
        "simulation_type",
        "layout",
        "motion",
        "interaction",
        "space",
        "placement_hint",
        mode="before",
    )
    @classmethod
    def normalize_text_field(cls, value: object) -> object:
        if isinstance(value, list):
            lines = []
            for item in value:
                if isinstance(item, str):
                    text = item.strip()
                elif isinstance(item, dict):
                    text = json.dumps(item, ensure_ascii=False)
                else:
                    text = str(item).strip()
                if text:
                    lines.append(text)
            return "\n".join(lines)
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return value

    @field_validator("animation_id", "title", "concept")
    @classmethod
    def require_text_field(cls, value: str, info) -> str:
        return _required_text(value, info.field_name)

    @field_validator("visual_elements")
    @classmethod
    def require_visual_elements(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("visual_elements must not be empty")
        return value

    @field_validator("success_check", mode="before")
    @classmethod
    def normalize_success_check(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        return value

    @model_validator(mode="after")
    def validate_simulation_contract(self) -> "SectionAnimationBriefOutput":
        has_simulation_fields = any(
            [
                self.target_markdown_heading,
                self.target_paragraph_summary,
                self.simulation_type,
                self.timeline,
                self.layout,
                self.interaction,
                self.success_check,
            ]
        )
        if has_simulation_fields and self.visual_model is None:
            raise ValueError("visual_model is required for simulation animation brief")
        if self.visual_model is not None and not self.timeline:
            raise ValueError("timeline is required for simulation animation brief")
        return self


class SectionVideoBriefOutput(BaseModel):
    video_id: str = Field(description="视频 brief ID")
    title: str = Field(description="视频检索标题")
    target_markdown_heading: str = Field(
        default="", description="服务的 Markdown 二级标题"
    )
    target_paragraph_summary: str = Field(default="", description="服务的正文段落摘要")
    search_terms: list[str] = Field(default_factory=list, description="检索关键词")
    purpose: str = Field(description="视频用途说明")

    @field_validator(
        "video_id",
        "title",
        "target_markdown_heading",
        "target_paragraph_summary",
        "purpose",
    )
    @classmethod
    def require_text_field(cls, value: str, info) -> str:
        if info.field_name in {"target_markdown_heading", "target_paragraph_summary"}:
            return str(value).strip()
        return _required_text(value, info.field_name)

    @field_validator("search_terms")
    @classmethod
    def require_search_terms(cls, value: list[str]) -> list[str]:
        if not value:
            return []
        terms = [_required_text(item, "search_terms") for item in value]
        if len(terms) < 3:
            raise ValueError("search_terms must contain at least three items")
        return terms

    @model_validator(mode="after")
    def reject_generic_purpose(self) -> "SectionVideoBriefOutput":
        if self.purpose.strip() in {"帮助理解本节内容", "辅助理解本节内容"}:
            raise ValueError("video brief purpose is too generic")
        return self


class SectionMarkdownOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(description="小节 ID")
    parent_section_id: str | None = Field(description="父章节 ID")
    title: str = Field(description="小节标题")
    markdown: str = Field(description="完整 Markdown 教学内容")
    source_references: list[SectionSourceReferenceOutput] = Field(default_factory=list)
    video_briefs: list[SectionVideoBriefOutput] = Field(default_factory=list)
    animation_briefs: list[SectionAnimationBriefOutput] = Field(default_factory=list)
    recommendation_reason: str = Field(
        default="", description="推荐理由，关联用户画像维度"
    )

    @field_validator("section_id", "title", "markdown")
    @classmethod
    def require_text_field(cls, value: str, info) -> str:
        return _required_text(value, info.field_name)

    @model_validator(mode="after")
    def validate_resource_contract(self) -> "SectionMarkdownOutput":
        if not self.video_briefs:
            raise ValueError("video_briefs must contain at least one item")
        if not self.animation_briefs:
            raise ValueError("animation_briefs must contain at least one item")
        if any(
            marker in self.markdown for marker in _SECTION_MARKDOWN_LOW_QUALITY_MARKERS
        ):
            raise ValueError("markdown must not contain low quality fallback markers")
        missing_headings = [
            heading
            for heading in _SECTION_MARKDOWN_REQUIRED_HEADINGS
            if not _has_markdown_heading(self.markdown, heading)
        ]
        if missing_headings:
            raise ValueError(
                "markdown missing required teaching headings: "
                f"{', '.join(missing_headings)}"
            )
        if not _has_markdown_heading(self.markdown, "来源"):
            raise ValueError("markdown missing required source heading: 来源")
        if not _has_unique_terminal_markdown_level_two_heading(self.markdown, "来源"):
            raise ValueError(
                "markdown source footer must be the final level two heading"
            )
        if not _markdown_heading_body(self.markdown, "来源"):
            raise ValueError("markdown source footer must not be empty")

        video_ids = {brief.video_id for brief in self.video_briefs}
        animation_ids = {brief.animation_id for brief in self.animation_briefs}
        markdown_video_ids = _placeholder_ids(self.markdown, "video")
        markdown_animation_ids = _placeholder_ids(self.markdown, "animation")
        if markdown_video_ids != video_ids:
            raise ValueError(
                "markdown video placeholders must exactly match video_briefs.video_id"
            )
        if markdown_animation_ids != animation_ids:
            raise ValueError(
                "markdown animation placeholders must exactly match "
                "animation_briefs.animation_id"
            )
        return self


class SectionVideoItemOutput(BaseModel):
    brief_id: str = Field(description="对应 video_briefs.video_id")
    title: str = Field(description="视频标题")
    url: str = Field(description="视频页面 URL")
    cover_url: str = Field(default="", description="视频封面 URL")
    source: str = Field(default="", description="视频来源站点")

    @field_validator("brief_id", "title", "url", "source")
    @classmethod
    def require_text_field(cls, value: str, info) -> str:
        return _required_text(value, info.field_name)

    @field_validator("url")
    @classmethod
    def require_http_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be an HTTP(S) video page URL")
        return value


class SectionVideoSearchOutput(BaseModel):
    section_id: str = Field(default="", description="小节 ID")
    query: str = Field(default="", description="实际搜索查询")
    status: Literal["available", "unavailable"] = Field(default="available")
    failure_reason: str = Field(default="")
    videos: list[SectionVideoItemOutput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status_payload(self) -> "SectionVideoSearchOutput":
        if self.status == "available" and not self.videos:
            raise ValueError("available video output must contain at least one item")
        if self.status == "unavailable" and not self.failure_reason.strip():
            raise ValueError("unavailable video output must include failure_reason")
        return self


class SectionHtmlAnimationItemOutput(BaseModel):
    animation_id: str = Field(description="动画 ID")
    title: str = Field(default="", description="动画标题")
    html: str = Field(description="可嵌入 HTML 片段")

    @field_validator("animation_id", "html")
    @classmethod
    def require_text_field(cls, value: str, info) -> str:
        return _required_text(value, info.field_name)

    @field_validator("html")
    @classmethod
    def require_section_animation_contract(cls, value: str) -> str:
        if "section-animation" not in value:
            raise ValueError('html must include class="section-animation"')
        if _DISALLOWED_HTML_COLOR_PATTERN.search(value):
            raise ValueError(
                "html must use OKLCH colors or CSS variables, not HEX/RGB/HSL"
            )
        return value


class SectionHtmlAnimationOutput(BaseModel):
    section_id: str = Field(default="", description="小节 ID")
    animations: list[SectionHtmlAnimationItemOutput] = Field(default_factory=list)

    @field_validator("animations")
    @classmethod
    def require_animations(
        cls, value: list[SectionHtmlAnimationItemOutput]
    ) -> list[SectionHtmlAnimationItemOutput]:
        if not value:
            raise ValueError("animations must contain at least one item")
        return value
