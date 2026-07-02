from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from app.orchestration.contracts import PhaseName


def checkpoint_for_phase(outline: dict, section_id: str, phase: PhaseName) -> dict:
    checkpoints = outline.get("section_resource_checkpoints")
    if not isinstance(checkpoints, dict):
        return {}
    section_checkpoints = checkpoints.get(section_id)
    if not isinstance(section_checkpoints, dict):
        return {}
    value = section_checkpoints.get(phase)
    return value if isinstance(value, dict) else {}


def section_phase_completed(outline: dict, section_id: str, phase: PhaseName) -> bool:
    return checkpoint_for_phase(outline, section_id, phase).get("status") == "completed"


def update_section_phase_checkpoint(
    outline: dict,
    *,
    section_id: str,
    phase: PhaseName,
    status: str,
    output_refs: dict | None = None,
    quality_result: dict | None = None,
    failure_reason: str = "",
    updated_at: str | None = None,
) -> dict:
    updated = deepcopy(outline)
    checkpoints = updated.setdefault("section_resource_checkpoints", {})
    section_checkpoints = checkpoints.setdefault(section_id, {})
    phase_checkpoint = {
        "status": status,
        "updated_at": updated_at or datetime.now(timezone.utc).isoformat(),
        "output_refs": output_refs or {},
        "quality_result": quality_result or {},
    }
    if failure_reason:
        phase_checkpoint["failure_reason"] = failure_reason
    section_checkpoints[phase] = phase_checkpoint
    return updated
