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
from app.orchestration.guards import (
    require_confirmed_intake_for_learning_path,
    require_course_source_for_course_knowledge,
    require_profile_for_intake,
    require_section_source_for_markdown,
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


def test_contract_error_defaults_to_blocking_quality_result() -> None:
    error = ContractError(
        "learning_path_agent",
        "path",
        "intake is not confirmed",
    )

    assert error.quality_result.to_dict() == {
        "passed": False,
        "severity": "blocking",
        "reason": "intake is not confirmed",
        "checks": [],
    }


def test_profile_guard_requires_basic_profile() -> None:
    require_profile_for_intake(
        {
            "profile": {
                "type": "basic_profile",
                "confirmed_info": {"current_grade": "大三"},
            }
        }
    )

    with pytest.raises(ContractError) as exc_info:
        require_profile_for_intake({"profile": {"type": "collecting"}})

    assert exc_info.value.agent == "learning_path_intake_agent"
    assert exc_info.value.phase == "intake"
    assert exc_info.value.quality_result.reason == "profile is not complete"


def test_learning_path_guard_requires_confirmed_intake() -> None:
    require_confirmed_intake_for_learning_path(
        {"learning_path_intake": {"status": "confirmed", "courses": []}}
    )

    with pytest.raises(ContractError) as exc_info:
        require_confirmed_intake_for_learning_path(
            {"learning_path_intake": {"status": "draft", "courses": []}}
        )

    assert exc_info.value.agent == "learning_path_agent"
    assert exc_info.value.phase == "path"
    assert (
        exc_info.value.quality_result.reason
        == "learning_path_intake.status is not confirmed"
    )


def test_course_knowledge_guard_requires_course_source_binding() -> None:
    require_course_source_for_course_knowledge(
        {
            "course_node_id": "year_3_course_1",
            "source_textbook_id": "textbook-ai-web",
            "source_outline_section_ids": ["1.1"],
        }
    )

    with pytest.raises(ContractError) as exc_info:
        require_course_source_for_course_knowledge(
            {"course_node_id": "year_3_course_1", "source_outline_section_ids": []}
        )

    assert exc_info.value.agent == "course_knowledge_agent"
    assert exc_info.value.phase == "outline"
    assert exc_info.value.quality_result.reason == "course source binding is incomplete"


def test_markdown_guard_requires_section_source_binding() -> None:
    require_section_source_for_markdown(
        {
            "section_id": "1.1",
            "source_textbook_id": "textbook-ai-web",
            "source_section_ids": ["1.1"],
        }
    )

    with pytest.raises(ContractError) as exc_info:
        require_section_source_for_markdown({"section_id": "1.1"})

    assert exc_info.value.agent == "section_markdown_agent"
    assert exc_info.value.phase == "markdown"
    assert (
        exc_info.value.quality_result.reason == "section source binding is incomplete"
    )
