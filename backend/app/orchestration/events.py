from __future__ import annotations

from app.orchestration.contracts import AgentName, PhaseName, QualityResult, agent_order


def build_agent_event(
    *,
    event: str,
    agent: AgentName,
    phase: PhaseName,
    status: str,
    step_id: str,
    message: str = "",
    depends_on: list[AgentName] | None = None,
    input_refs: dict[str, object] | None = None,
    output_refs: dict[str, object] | None = None,
    quality_result: QualityResult | dict[str, object] | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "event": event,
        "agent": agent,
        "agent_order": agent_order(agent),
        "phase": phase,
        "status": status,
        "stepId": step_id,
        "depends_on": depends_on or [],
        "input_refs": input_refs or {},
        "output_refs": output_refs or {},
        "quality_result": _quality_payload(quality_result),
    }
    if message:
        payload["message"] = message
    if extra:
        payload.update(extra)
    return payload


def _quality_payload(
    value: QualityResult | dict[str, object] | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    if isinstance(value, QualityResult):
        return value.to_dict()
    return value
