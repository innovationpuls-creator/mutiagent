from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProfileConfirmedInfo(BaseModel):
    current_grade: str = ""
    major: str = ""
    learning_stage: str = ""
    has_clear_goal: str = ""
    learning_method_preference: str = ""
    learning_pace_preference: str = ""
    content_preference: list[str] = Field(default_factory=list)
    need_guidance: str = ""
    knowledge_foundation: str = ""
    strengths: str = ""
    weaknesses: str = ""
    experience: str = ""
    short_term_goal: str = ""
    long_term_goal: str = ""
    weekly_available_time: str = ""
    constraints: str = ""


class QuestionBoxOption(BaseModel):
    label: str
    value: str
    description: str = ""
    target_fields: list[str] = Field(default_factory=list)
    fills: dict[str, str | list[str]] = Field(default_factory=dict)


class QuestionBoxData(BaseModel):
    question: str = ""
    options: list[QuestionBoxOption] = Field(default_factory=list)


class ProfileAgentOutput(BaseModel):
    type: Literal["collecting", "basic_profile"]
    stage: Literal["basic_info", "learning_preference", "ability_basis", "goal_constraint", "generated"]
    question_mode: Literal["question_md", "question_box", "none"]
    confirmed_info: ProfileConfirmedInfo = Field(default_factory=ProfileConfirmedInfo)
    defaulted_fields: list[str] = Field(default_factory=list)
    question_md: str = ""
    question_box: QuestionBoxData = Field(default_factory=QuestionBoxData)
    text: str = ""


class LearningPathRequest(BaseModel):
    learning_topic: str = ""
    goal: str = ""
    preference: str = ""
    target_time: str = ""
    desired_outcome: str = ""
