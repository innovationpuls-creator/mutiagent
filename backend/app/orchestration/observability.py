from __future__ import annotations

from app.orchestration.contracts import AgentName, PhaseName

_BLOCKED_TRACE_KEYS = {
    "evidence_text",
    "markdown",
    "html",
    "previous_html",
    "textbook_evidence_pack",
}


def _compact_mapping(value: dict) -> dict:
    compact: dict = {}
    for key, item in value.items():
        if key in _BLOCKED_TRACE_KEYS:
            continue
        if isinstance(item, str) and len(item) > 500:
            compact[f"{key}_length"] = len(item)
            continue
        compact[key] = item
    return compact


def build_agent_trace(
    *,
    trace_id: str,
    agent: AgentName,
    phase: PhaseName,
    started_at_ms: int,
    ended_at_ms: int,
    input_summary: dict,
    output_summary: dict,
    failure_reason: str = "",
) -> dict:
    return {
        "trace_id": trace_id,
        "agent": agent,
        "phase": phase,
        "duration_ms": max(0, ended_at_ms - started_at_ms),
        "input_summary": _compact_mapping(input_summary),
        "output_summary": _compact_mapping(output_summary),
        "failure_reason": failure_reason,
    }
