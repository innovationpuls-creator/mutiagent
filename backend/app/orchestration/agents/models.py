"""Simplified Pydantic output models for structured LLM generation.

Uses `with_structured_output` — no manual JSON parsing.
Models are permissive (no extra="forbid") to allow LLM flexibiliy.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Profile Agent ────────────────────────────────────────────────────────

ChatStage = Literal["basic_info", "learning_preference", "ability_basis", "goal_constraint", "generated"]
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
ResourceType = Literal["学习资源", "题库", "文档", "代码示例", "视频脚本", "动态更新任务"]
DifficultyLevel = Literal["入门", "基础", "中级", "高级"]
GoalType = Literal["考试", "课程学习", "项目实践", "能力提升", "就业准备", "其他"]
REQUIRED_GRADE_PLAN_KEYS = frozenset({"year_1", "year_2", "year_3", "year_4"})


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


class QuestionBoxOptionOutput(BaseModel):
    """SessionMessage question_box.options 单项。"""
    label: str = Field(description="选项展示文本")
    value: str = Field(description="选项值")
    description: str = Field(description="选项说明")
    target_fields: list[str] = Field(description="该选项影响的字段")
    fills: dict[str, str | list[str]] = Field(description="该选项填充的字段值")


class QuestionBoxOutput(BaseModel):
    """SessionMessage question_box 结构。"""
    question: str = Field(description="问题文本")
    options: list[QuestionBoxOptionOutput] = Field(description="可选答案")


class ProfileSessionOutput(BaseModel):
    """画像 Agent 的 SessionMessage 兼容结构化输出。"""
    type: Literal["collecting", "basic_profile"] = Field(description="消息类型")
    stage: ChatStage = Field(description="当前画像阶段")
    question_mode: QuestionMode = Field(description="提问模式")
    confirmed_info: ConfirmedInfoOutput = Field(description="已确认画像信息")
    defaulted_fields: list[str] = Field(description="由系统补全的字段")
    question_md: str = Field(description="Markdown 问题文本")
    question_box: QuestionBoxOutput = Field(description="结构化问题框")
    text: str = Field(description="自然语言回复文本")


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
    course_node_id: str = Field(description="课程节点 ID")
    grade_id: GradeId = Field(description="所属年级 ID")
    course_or_chapter_theme: str = Field(description="课程或章节主题")
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
    progress_state: Literal["not_started", "in_progress", "paused", "completed"] = Field(description="进度状态")
    next_action: str = Field(description="下一步行动")


class LearningPathResultOutput(BaseModel):
    """learning_path.v2.course_node 学习路径输出。"""
    schema_version: Literal["learning_path.v2.course_node"] = Field(description="学习路径契约版本")
    learning_goal: LearningGoalOutput = Field(description="学习目标")
    learner_baseline: LearnerBaselineOutput = Field(description="学习者基线")
    planning_rules: PlanningRulesOutput = Field(description="规划规则")
    grade_plans: dict[GradeId, GradePlanOutput] = Field(description="年级计划")
    knowledge_graph: KnowledgeGraphOutput = Field(description="知识图谱")
    resource_generation_contract: ResourceGenerationContractOutput = Field(description="资源生成契约")
    dynamic_update_contract: DynamicUpdateContractOutput = Field(description="动态更新契约")
    current_learning_courses: list[CurrentLearningCourse] = Field(default_factory=list, description="当前学习课程列表")
    current_learning_course: CurrentLearningCourse = Field(description="当前学习课程")



    @model_validator(mode="after")
    def normalize_current_learning_courses(self) -> "LearningPathResultOutput":
        current_courses = list(self.current_learning_courses)
        if not current_courses:
            current_courses = [self.current_learning_course]

        first_course = current_courses[0]
        if self.current_learning_course != first_course:
            self.current_learning_course = first_course
        self.current_learning_courses = current_courses
        return self


ProfileOutput = ProfileSessionOutput
YearLearningPathOutput = LearningPathResultOutput


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


class SectionDraftItem(BaseModel):
    """章节草稿 — 允许 LLM 返回不完整字段，由本地补齐。"""
    section_id: str | None = Field(default=None, description="节 ID，如 1, 1.1, 1.1.1")
    parent_section_id: str | None = Field(default=None, description="父节 ID，顶层为 null")
    depth: int | None = Field(default=None, ge=1, le=4, description="层级深度 1-4")
    title: str = Field(description="标题")
    order_index: int | None = Field(default=None, ge=1, description="排序索引")
    description: str = Field(default="", description="简要说明")
    key_knowledge_points: list[str] = Field(default_factory=list, description="核心知识点")


class CourseKnowledgeOutput(BaseModel):
    """课程大纲 — 详版。"""
    course_id: str = Field(description="课程 ID")
    course_name: str = Field(description="课程名称")
    grade_year: str = Field(description="所属年级")
    personalization_summary: str = Field(description="个性化安排说明")
    sections: list[SectionItem] = Field(description="章节列表，含层级关系")
    learning_sequence: list[str] = Field(description="推荐学习步骤，使用面向用户的自然语言短句列表")
    total_estimated_hours: str = Field(description="预计总学时")


class CourseKnowledgeDraftOutput(BaseModel):
    """课程大纲草稿 — 允许 LLM 返回半结构化内容，由本地规范化。"""
    course_id: str | None = Field(default=None, description="课程 ID")
    course_name: str | None = Field(default=None, description="课程名称")
    grade_year: str | None = Field(default=None, description="所属年级")
    personalization_summary: str = Field(default="", description="个性化安排说明")
    sections: list[SectionDraftItem] = Field(default_factory=list, description="章节列表，允许字段不完整")
    learning_sequence: list[str] = Field(default_factory=list, description="推荐学习步骤，可返回章节编号或面向用户的自然语言短句")
    total_estimated_hours: str | int | None = Field(default=None, description="预计总学时")
