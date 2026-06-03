from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

DEFAULT_TTL_SECONDS = 7200  # 2 hours


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
    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._executions: dict[str, ExecutionState] = {}
        self._ttl_seconds = ttl_seconds

    def _purge_expired(self) -> None:
        """Remove entries older than TTL to prevent unbounded memory growth."""
        now = datetime.now(timezone.utc)
        expired = [
            eid
            for eid, state in self._executions.items()
            if (now - state.updated_at).total_seconds() > self._ttl_seconds
        ]
        for eid in expired:
            del self._executions[eid]

    def create(self, user_id: str) -> ExecutionState:
        self._purge_expired()
        execution = ExecutionState(execution_id=str(uuid4()), user_id=user_id)
        self._executions[execution.execution_id] = execution
        return execution

    def get(self, execution_id: str) -> ExecutionState | None:
        state = self._executions.get(execution_id)
        if state is None:
            return None
        # Check if expired
        elapsed = (datetime.now(timezone.utc) - state.updated_at).total_seconds()
        if elapsed > self._ttl_seconds:
            del self._executions[execution_id]
            return None
        return state

    def save(self, execution: ExecutionState) -> None:
        execution.updated_at = datetime.now(timezone.utc)
        self._executions[execution.execution_id] = execution


registry = ExecutionRegistry()
