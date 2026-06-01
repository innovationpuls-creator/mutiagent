from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


AgentKey = Literal["intent_recognition_agent", "profile_agent", "learning_path_agent"]
AgentAction = Literal["reply_only", "call_agents", "final_answer"]
GoalType = Literal["考试", "课程学习", "项目实践", "能力提升", "就业准备", "其他"]


class QuestionBox(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    options: list[str]


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


class LearningGoal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_course_or_skill: str = Field(min_length=1)
    target_completion_time: str = Field(min_length=1)
    goal_type: GoalType
    desired_outcome: str = Field(min_length=1)


class GapAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_mastered_content: list[str] = Field(min_length=1)
    current_weaknesses: list[str] = Field(min_length=1)
    required_capabilities: list[str] = Field(min_length=1)
    main_gaps: list[str] = Field(min_length=1)


class FoundationStage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_id: str = Field(min_length=1)
    stage_name: str = Field(min_length=1)
    learning_goal: str = Field(min_length=1)
    learning_content: list[str] = Field(min_length=1)
    learning_tasks: list[str] = Field(min_length=1)
    recommended_methods: list[str] = Field(min_length=1)
    completion_standard: list[str] = Field(min_length=1)


class FoundationPath(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stages: list[FoundationStage] = Field(min_length=1)


class StageRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_id: str = Field(min_length=1)
    route_summary: str = Field(min_length=1)


class ScheduleItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: str = Field(min_length=1)
    focus: str = Field(min_length=1)
    milestone: str = Field(min_length=1)


class StageAcceptanceCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_id: str = Field(min_length=1)
    criteria: list[str] = Field(min_length=1)


class GeneratedPath(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_goal: str = Field(min_length=1)
    stage_routes: list[StageRoute] = Field(min_length=1)
    schedule: list[ScheduleItem] = Field(min_length=1)
    task_checklist: list[str] = Field(min_length=1)
    recommended_resource_types: list[str] = Field(min_length=1)
    stage_acceptance_criteria: list[StageAcceptanceCriteria] = Field(min_length=1)
    next_actions: list[str] = Field(min_length=1)


class LearningPathResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    learning_goal: LearningGoal
    gap_analysis: GapAnalysis
    foundation_path: FoundationPath
    generated_path: GeneratedPath
