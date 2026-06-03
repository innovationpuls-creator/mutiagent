"""Shared utilities for agent nodes."""

from __future__ import annotations

from app.orchestration.state import OrchestrationState


def extract_last_tool_call_id(state: OrchestrationState) -> str | None:
    """Walk messages in reverse to find the most recent tool_call id."""
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            return msg.tool_calls[0].get("id")
    return None


def extract_last_tool_call_args(state: OrchestrationState) -> dict:
    """Walk messages in reverse to find the most recent tool_call args."""
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            return msg.tool_calls[0].get("args", {})
    return {}
