"""Shared utilities for agent nodes — extracted from duplicated code across agents."""

from __future__ import annotations

import json
import re

from app.orchestration.state import OrchestrationState


def parse_json_response(text: str) -> dict:
    """Extract JSON from LLM response, supporting both code-block and raw formats."""
    text = text.strip()

    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        text = json_match.group(1).strip()

    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        return json.loads(text)

    raise ValueError(f"Response does not contain valid JSON: {text[:200]}")


def extract_last_tool_call_id(state: OrchestrationState) -> str | None:
    """Walk messages in reverse to find the most recent tool_call id."""
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            return msg.tool_calls[0].get("id")
    return None
