from __future__ import annotations

from typing import Annotated, Optional

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict


class OrchestrationState(TypedDict):
    query: str
    user_id: str
    session_id: str
    messages: Annotated[list[BaseMessage], add_messages]

    profile: Optional[dict]
    learning_path: Optional[dict]
    course_knowledge: Optional[dict]

    response: str
    answer: Optional[dict]
    question_box: Optional[dict]
    profile_completed: Optional[bool]
    error: Optional[str]
