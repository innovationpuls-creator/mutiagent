from __future__ import annotations

from typing import Annotated, Optional

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict


class OrchestrationState(TypedDict, total=False):
    """Orchestration state for the multi-agent LangGraph.

    All agent output and DB-loaded data is stored here.
    No checkpoint persistence — state is rebuilt from DB each turn.
    """
    # Input
    user_id: str
    session_id: str
    query: str

    # Conversation (managed by LangGraph's add_messages)
    messages: Annotated[list[BaseMessage], add_messages]

    # DB-loaded context
    profile: Optional[dict]
    learning_path_intake: Optional[dict]
    year_learning_paths: Optional[dict]  # {year_1: YearLearningPathOutput, ...}
    course_knowledge: Optional[dict]      # most recent CourseKnowledgeOutput
    course_knowledges: Optional[list[dict]]

    # Agent outputs for this turn
    response: Optional[str]
    grade_year: Optional[str]
    latest_grade_year: Optional[str]
    course_resource_plan: Optional[dict]
    course_resource_result: Optional[dict]
