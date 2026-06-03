from __future__ import annotations

from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AgentKey = Literal[
    "intent_recognition_agent",
    "profile_agent",
    "learning_path_agent",
    "course_knowledge_agent",
]
AgentAction = Literal["reply_only", "call_agents", "final_answer"]
GoalType = Literal["考试", "课程学习", "项目实践", "能力提升", "就业准备", "其他"]
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
GRADE_PLAN_KEYS: tuple[GradeId, ...] = ("year_1", "year_2", "year_3", "year_4")
KNOWLEDGE_POINT_LEVEL_ALIASES: dict[str, KnowledgePointLevel] = {"高级": "进阶"}


class QuestionBoxOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    value: str
    description: str
    target_fields: list[str]
    fills: dict[str, str | list[str]]

    @model_validator(mode="before")
    @classmethod
    def convert_from_string(cls, data: object) -> object:
        if isinstance(data, str):
            return {
                "label": data,
                "value": data,
                "description": "",
                "target_fields": ["query"],
                "fills": {"query": data},
            }
        return data


class QuestionBox(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    options: list[QuestionBoxOption]


class MainAgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_message: str = Field(min_length=1)
    question_box: QuestionBox | None


class AgentCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    agent_key: AgentKey
    label: str = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    parallel_group: str | None
    agent_input: dict


class CourseKnowledgeSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(pattern=r"^[0-9]+(\.[0-9]+)*$")
    parent_section_id: str | None
    depth: int = Field(ge=1, le=4)
    title: str = Field(min_length=1)
    order_index: int = Field(ge=1)


class CourseKnowledgeOutlineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["course_knowledge_outline.v1"]
    course_node_id: str = Field(min_length=1)
    course_name: str = Field(min_length=1)
    grade_id: GradeId
    personalization_summary: str = Field(min_length=1)
    sections: list[CourseKnowledgeSection] = Field(min_length=1)
    learning_sequence: list[str] = Field(min_length=1)
    markmap_source: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_section_graph(self) -> "CourseKnowledgeOutlineResult":
        section_ids = [section.section_id for section in self.sections]
        if len(set(section_ids)) != len(section_ids):
            raise ValueError("section_id values must be unique")

        sections_by_id = {section.section_id: section for section in self.sections}
        for section in self.sections:
            if section.parent_section_id is None:
                if section.depth != 1:
                    raise ValueError("top-level section depth must be 1")
                continue

            parent = sections_by_id.get(section.parent_section_id)
            if parent is None:
                raise ValueError("parent_section_id references unknown section_id")
            if parent.depth + 1 != section.depth:
                raise ValueError("section depth must follow parent depth")

        unknown_sequence_ids = [
            section_id
            for section_id in self.learning_sequence
            if section_id not in sections_by_id
        ]
        if unknown_sequence_ids:
            raise ValueError("learning_sequence references unknown section_id")
        return self


class MainAgentControl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: AgentAction
    calls: list[AgentCall]

    @field_validator("calls")
    @classmethod
    def validate_calls_for_action(cls, calls: list[AgentCall], info: object) -> list[AgentCall]:
        data = getattr(info, "data", {})
        action = data.get("action")
        if action in {"reply_only", "final_answer"} and calls:
            raise ValueError("calls must be empty when action is reply_only or final_answer")
        if action == "call_agents" and not calls:
            raise ValueError("calls must not be empty when action is call_agents")
        return calls


class MainAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: MainAgentResponse
    control: MainAgentControl


def validate_call_graph(calls: list[AgentCall]) -> None:
    ids = {call.call_id for call in calls}
    if len(ids) != len(calls):
        raise ValueError("call_id values must be unique")
    for call in calls:
        for dependency in call.depends_on:
            if dependency not in ids:
                raise ValueError("depends_on references unknown call_id")
            if dependency == call.call_id:
                raise ValueError("depends_on must not reference the same call_id")


def _filled_string(value: object) -> str:
    return value if isinstance(value, str) and value.strip() else ""


def _filled_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _core_knowledge_point_ids(course_node: dict) -> list[str]:
    points = course_node.get("core_knowledge_points")
    if not isinstance(points, list):
        return []
    ids: list[str] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        knowledge_point_id = _filled_string(point.get("knowledge_point_id"))
        if knowledge_point_id:
            ids.append(knowledge_point_id)
    return ids


def _normalize_knowledge_point_levels(course_node: dict) -> None:
    points = course_node.get("core_knowledge_points")
    if not isinstance(points, list):
        return
    for point in points:
        if not isinstance(point, dict):
            continue
        level = point.get("level")
        if isinstance(level, str) and level in KNOWLEDGE_POINT_LEVEL_ALIASES:
            point["level"] = KNOWLEDGE_POINT_LEVEL_ALIASES[level]


def _fallback_knowledge_point(course_node: dict) -> dict | None:
    course_node_id = _filled_string(course_node.get("course_node_id"))
    theme = _filled_string(course_node.get("course_or_chapter_theme"))
    course_goal = _filled_string(course_node.get("course_goal"))
    if not course_node_id or not theme or not course_goal:
        return None

    return {
        "knowledge_point_id": f"kp_{course_node_id}",
        "name": theme,
        "parent_knowledge_point_id": None,
        "level": "核心",
        "description": course_goal,
        "mastery_standard": course_goal,
    }


def _normalize_core_knowledge_points(course_node: dict) -> None:
    points = course_node.get("core_knowledge_points")
    if not isinstance(points, list) or points:
        return
    point = _fallback_knowledge_point(course_node)
    if point is not None:
        course_node["core_knowledge_points"] = [point]


def _fallback_chapter_relation(course_node: dict, chapter_node_id: str) -> dict | None:
    knowledge_point_ids = _core_knowledge_point_ids(course_node)
    if not knowledge_point_ids:
        return None
    return {
        "from_node_id": knowledge_point_ids[0],
        "to_node_id": chapter_node_id,
        "relation_type": "contains",
        "description": "章节包含课程节点的核心知识点",
    }


def _fallback_course_relation(course_node: dict) -> dict | None:
    course_node_id = _filled_string(course_node.get("course_node_id"))
    if not course_node_id:
        return None

    chapter_nodes = course_node.get("chapter_nodes")
    if not isinstance(chapter_nodes, list) or not chapter_nodes:
        return None

    first_chapter = chapter_nodes[0]
    if not isinstance(first_chapter, dict):
        return None
    chapter_node_id = _filled_string(first_chapter.get("chapter_node_id"))
    if not chapter_node_id:
        return None

    return {
        "from_node_id": chapter_node_id,
        "to_node_id": course_node_id,
        "relation_type": "contains",
        "description": "课程节点包含章节节点",
    }


def _fallback_chapter_node(course_node: dict) -> dict | None:
    course_node_id = _filled_string(course_node.get("course_node_id"))
    theme = _filled_string(course_node.get("course_or_chapter_theme"))
    course_goal = _filled_string(course_node.get("course_goal"))
    knowledge_point_ids = _core_knowledge_point_ids(course_node)
    if not course_node_id or not theme or not course_goal or not knowledge_point_ids:
        return None

    chapter_node_id = f"{course_node_id}_chapter_1"
    relation = _fallback_chapter_relation(course_node, chapter_node_id)
    if relation is None:
        return None

    return {
        "chapter_node_id": chapter_node_id,
        "chapter_theme": theme,
        "knowledge_hierarchy": [
            {
                "hierarchy_id": f"hier_{chapter_node_id}",
                "parent_hierarchy_id": None,
                "hierarchy_level": "课程",
                "title": theme,
                "summary": course_goal,
                "knowledge_point_ids": knowledge_point_ids,
            }
        ],
        "core_knowledge_point_ids": knowledge_point_ids,
        "key_points": _filled_string_list(course_node.get("key_points")),
        "difficult_points": _filled_string_list(course_node.get("difficult_points")),
        "prerequisite_node_ids": _filled_string_list(course_node.get("prerequisite_node_ids")),
        "learning_sequence": _filled_string_list(course_node.get("learning_sequence")),
        "knowledge_relations": [relation],
        "downstream_resource_direction_ids": _filled_string_list(
            course_node.get("downstream_resource_direction_ids")
        ),
    }


def _normalize_chapter_nodes(course_node: dict) -> None:
    chapter_nodes = course_node.get("chapter_nodes")
    if not isinstance(chapter_nodes, list):
        return

    if not chapter_nodes:
        chapter_node = _fallback_chapter_node(course_node)
        if chapter_node is not None:
            course_node["chapter_nodes"] = [chapter_node]
        return

    for chapter_node in chapter_nodes:
        if not isinstance(chapter_node, dict):
            continue
        relations = chapter_node.get("knowledge_relations")
        if isinstance(relations, list) and not relations:
            chapter_node_id = _filled_string(chapter_node.get("chapter_node_id"))
            relation = _fallback_chapter_relation(course_node, chapter_node_id)
            if relation is not None:
                chapter_node["knowledge_relations"] = [relation]


def _normalize_course_relations(course_node: dict) -> None:
    relations = course_node.get("knowledge_relations")
    if not isinstance(relations, list) or relations:
        return
    relation = _fallback_course_relation(course_node)
    if relation is not None:
        course_node["knowledge_relations"] = [relation]


def normalize_learning_path_result_payload(payload: dict) -> dict:
    normalized = deepcopy(payload)
    grade_plans = normalized.get("grade_plans")
    if not isinstance(grade_plans, dict):
        return normalized

    for grade_id in GRADE_PLAN_KEYS:
        grade_plan = grade_plans.get(grade_id)
        if not isinstance(grade_plan, dict):
            continue
        course_nodes = grade_plan.get("course_nodes")
        if not isinstance(course_nodes, list):
            continue
        for course_node in course_nodes:
            if not isinstance(course_node, dict):
                continue
            _normalize_core_knowledge_points(course_node)
            _normalize_knowledge_point_levels(course_node)
            _normalize_chapter_nodes(course_node)
            _normalize_course_relations(course_node)

    return normalized


class LearningGoal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_course_or_skill: str = Field(min_length=1)
    goal_type: GoalType
    desired_outcome: str = Field(min_length=1)
    four_year_outcome: str = Field(min_length=1)


class LearnerBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_grade: str = Field(min_length=1)
    major: str = Field(min_length=1)
    mastered_content: list[str] = Field(min_length=1)
    weaknesses: list[str] = Field(min_length=1)
    constraints: list[str] = Field(min_length=1)
    weekly_available_time: str = Field(min_length=1)


class PlanningRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_unit: Literal["course_node"]
    grade_boundary_rule: Literal[
        "每个 course_node 必须只属于一个 grade_id，不能跨年级安排；跨年级内容必须拆成多个 course_node。"
    ]
    sequence_rule: str = Field(min_length=1)
    resource_rule: str = Field(min_length=1)


class TimeArrangement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semester_scope: SemesterScope
    duration: str = Field(min_length=1)
    pace_reason: str = Field(min_length=1)


class KnowledgeHierarchyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hierarchy_id: str = Field(min_length=1)
    parent_hierarchy_id: str | None
    hierarchy_level: HierarchyLevel
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    knowledge_point_ids: list[str] = Field(min_length=1)


class KnowledgePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    knowledge_point_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    parent_knowledge_point_id: str | None
    level: KnowledgePointLevel
    description: str = Field(min_length=1)
    mastery_standard: str = Field(min_length=1)


class KnowledgeRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_node_id: str = Field(min_length=1)
    to_node_id: str = Field(min_length=1)
    relation_type: RelationType
    description: str = Field(min_length=1)


class ChapterNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_node_id: str = Field(min_length=1)
    chapter_theme: str = Field(min_length=1)
    knowledge_hierarchy: list[KnowledgeHierarchyItem] = Field(min_length=1)
    core_knowledge_point_ids: list[str] = Field(min_length=1)
    key_points: list[str] = Field(min_length=1)
    difficult_points: list[str] = Field(min_length=1)
    prerequisite_node_ids: list[str] = Field(default_factory=list)
    learning_sequence: list[str] = Field(min_length=1)
    knowledge_relations: list[KnowledgeRelation] = Field(min_length=1)
    downstream_resource_direction_ids: list[str] = Field(min_length=1)


class CourseNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_node_id: str = Field(min_length=1)
    grade_id: GradeId
    course_or_chapter_theme: str = Field(min_length=1)
    time_arrangement: TimeArrangement
    course_goal: str = Field(min_length=1)
    prerequisite_node_ids: list[str] = Field(default_factory=list)
    chapter_nodes: list[ChapterNode] = Field(min_length=1)
    core_knowledge_points: list[KnowledgePoint] = Field(min_length=1)
    key_points: list[str] = Field(min_length=1)
    difficult_points: list[str] = Field(min_length=1)
    learning_sequence: list[str] = Field(min_length=1)
    knowledge_relations: list[KnowledgeRelation] = Field(min_length=1)
    downstream_resource_direction_ids: list[str] = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)


class GradePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade_id: GradeId
    grade_name: str = Field(min_length=1)
    grade_goal: str = Field(min_length=1)
    course_nodes: list[CourseNode] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_course_node_grade_ids(self) -> "GradePlan":
        for course_node in self.course_nodes:
            if course_node.grade_id != self.grade_id:
                raise ValueError("course_node grade_id must match parent grade_id")
        return self


class GradePlans(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year_1: GradePlan
    year_2: GradePlan
    year_3: GradePlan
    year_4: GradePlan

    @model_validator(mode="after")
    def validate_grade_plan_keys(self) -> "GradePlans":
        expected_grade_ids: dict[str, GradeId] = {
            "year_1": "year_1",
            "year_2": "year_2",
            "year_3": "year_3",
            "year_4": "year_4",
        }
        for field_name, expected_grade_id in expected_grade_ids.items():
            grade_plan = getattr(self, field_name)
            if grade_plan.grade_id != expected_grade_id:
                raise ValueError("grade_plan grade_id must match grade_plans key")
        return self


class CriticalPath(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path_id: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    ordered_node_ids: list[str] = Field(min_length=1)


class KnowledgeGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    global_relations: list[KnowledgeRelation] = Field(min_length=1)
    critical_paths: list[CriticalPath] = Field(min_length=1)


class ResourceDirection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_direction_id: str = Field(min_length=1)
    target_node_ids: list[str] = Field(min_length=1)
    resource_type: ResourceType
    generation_goal: str = Field(min_length=1)
    content_requirements: list[str] = Field(min_length=1)
    difficulty_level: DifficultyLevel


class ResourceGenerationContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    downstream_agents: list[ResourceAgent] = Field(min_length=6)
    resource_directions: list[ResourceDirection] = Field(min_length=1)


class DynamicUpdateContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trackable_metrics: list[str] = Field(min_length=1)
    update_triggers: list[str] = Field(min_length=1)
    adjustment_strategy: str = Field(min_length=1)



class LearningPathResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["learning_path.v2.course_node"]
    learning_goal: LearningGoal
    learner_baseline: LearnerBaseline
    planning_rules: PlanningRules
    grade_plans: GradePlans
    knowledge_graph: KnowledgeGraph
    resource_generation_contract: ResourceGenerationContract
    dynamic_update_contract: DynamicUpdateContract
