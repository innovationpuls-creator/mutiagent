from __future__ import annotations

from app.orchestration.contracts import AgentName, PhaseName


def build_trace(
    *,
    agent: AgentName,
    phase: PhaseName,
    section_id: str = "",
    input_refs: dict[str, object] | None = None,
    output_refs: dict[str, object] | None = None,
    quality_result: dict[str, object] | None = None,
    duration_ms: int | None = None,
    failure_reason: str = "",
) -> dict[str, object]:
    trace: dict[str, object] = {
        "agent": agent,
        "phase": phase,
        "section_id": section_id,
        "input_refs": input_refs or {},
        "output_refs": output_refs or {},
        "quality_result": quality_result or {},
    }
    if duration_ms is not None:
        trace["duration_ms"] = duration_ms
    if failure_reason:
        trace["failure_reason"] = failure_reason
    return trace
