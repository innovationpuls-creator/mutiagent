from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class ExecutionState:
    execution_id: str
    user_id: str
    intent_conversation_id: str = ""
    conversation_id: str = ""
    completed: bool = False
    final_result: dict | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionRegistry:
    def __init__(self) -> None:
        self._executions: dict[str, ExecutionState] = {}

    def create(self, user_id: str) -> ExecutionState:
        execution = ExecutionState(execution_id=str(uuid4()), user_id=user_id)
        self._executions[execution.execution_id] = execution
        return execution

    def get(self, execution_id: str) -> ExecutionState | None:
        return self._executions.get(execution_id)

    def save(self, execution: ExecutionState) -> None:
        execution.updated_at = datetime.now(timezone.utc)
        self._executions[execution.execution_id] = execution


registry = ExecutionRegistry()
