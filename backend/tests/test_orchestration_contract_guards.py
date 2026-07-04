from __future__ import annotations

import pytest

from app.orchestration.contracts import (
    AGENT_ORDER,
    ContractError,
    QualityCheck,
    QualityResult,
    ResourceStatus,
    agent_order,
    quality_passed,
)


def test_agent_order_matches_learning_resource_pipeline() -> None:
    assert AGENT_ORDER == {
        "profile_agent": 1,
        "learning_path_intake_agent": 2,
        "learning_path_agent": 3,
        "course_knowledge_agent": 4,
        "section_markdown_agent": 5,
        "section_video_search_agent": 6,
        "section_html_animation_agent": 7,
        "compose_resource": 8,
    }
    assert agent_order("section_markdown_agent") == 5


def test_quality_result_shape_is_machine_checkable() -> None:
    result = QualityResult(
        passed=False,
        severity="blocking",
        reason="source_references is empty",
        checks=[
            QualityCheck(
                name="source_references_present",
                passed=False,
                reason="source_references is empty",
            )
        ],
    )

    assert result.to_dict() == {
        "passed": False,
        "severity": "blocking",
        "reason": "source_references is empty",
        "checks": [
            {
                "name": "source_references_present",
                "passed": False,
                "reason": "source_references is empty",
            }
        ],
    }


def test_quality_passed_helper_uses_informational_severity() -> None:
    assert quality_passed().to_dict() == {
        "passed": True,
        "severity": "informational",
        "reason": "",
        "checks": [],
    }


def test_resource_status_values_are_explicit() -> None:
    statuses: set[ResourceStatus] = {
        "available",
        "unavailable",
        "recoverable_failed",
        "blocking_failed",
    }

    assert "available" in statuses


def test_contract_error_carries_agent_phase_and_quality_result() -> None:
    quality = QualityResult(
        passed=False,
        severity="blocking",
        reason="intake is not confirmed",
    )
    error = ContractError(
        "learning_path_agent",
        "path",
        "intake is not confirmed",
        quality,
    )

    assert str(error) == "learning_path_agent:path:intake is not confirmed"
    assert error.agent == "learning_path_agent"
    assert error.phase == "path"
    assert error.quality_result is quality


def test_contract_error_is_value_error() -> None:
    with pytest.raises(ValueError):
        raise ContractError("learning_path_agent", "path", "intake is not confirmed")
