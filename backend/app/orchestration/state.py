from __future__ import annotations

from typing import TypedDict


class OrchestrationState(TypedDict):
    query: str
    user_id: str
    conversation_id: str
    intent_conversation_id: str
    intent_raw: dict
    intent: str
    route_status: str
    dify_raw: dict
    answer_json: dict
    phase: str
    error: str
