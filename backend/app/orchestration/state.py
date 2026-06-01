from __future__ import annotations

from typing import TypedDict


class OrchestrationState(TypedDict):
    query: str
    user_id: str
    session_id: str
    mode: str
    main_raw: dict
    main_result: dict
    agent_results: dict
    answer: dict
    agent_trace: list[dict]
    user_profile: dict
    profile: dict | None
    learning_path: dict | None
    awaiting_profile: bool
    completed: bool
    error: str
