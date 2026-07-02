from __future__ import annotations

from app.orchestration.contracts import quality_passed
from app.orchestration.events import build_agent_event
from app.orchestration.observability import build_agent_trace
from app.orchestration.recovery import (
    checkpoint_for_phase,
    section_phase_completed,
    update_section_phase_checkpoint,
)


def test_build_agent_event_includes_order_dependencies_refs_and_quality() -> None:
    event = build_agent_event(
        event="agent_result",
        agent="section_markdown_agent",
        phase="markdown",
        status="completed",
        step_id="leaf-section-1.1-markdown",
        message="Markdown completed",
        depends_on=["course_knowledge_agent"],
        input_refs={
            "course_id": "year_3_course_1",
            "section_id": "1.1",
            "source_textbook_id": "textbook-data-structures",
            "source_section_ids": ["2.3"],
        },
        output_refs={
            "section_markdown_id": "1.1",
            "video_brief_ids": ["video_1"],
            "animation_brief_ids": ["anim_1"],
        },
        quality_result=quality_passed(),
    )

    assert event == {
        "event": "agent_result",
        "agent": "section_markdown_agent",
        "agent_order": 5,
        "phase": "markdown",
        "status": "completed",
        "stepId": "leaf-section-1.1-markdown",
        "depends_on": ["course_knowledge_agent"],
        "input_refs": {
            "course_id": "year_3_course_1",
            "section_id": "1.1",
            "source_textbook_id": "textbook-data-structures",
            "source_section_ids": ["2.3"],
        },
        "output_refs": {
            "section_markdown_id": "1.1",
            "video_brief_ids": ["video_1"],
            "animation_brief_ids": ["anim_1"],
        },
        "quality_result": {
            "passed": True,
            "severity": "informational",
            "reason": "",
            "checks": [],
        },
        "message": "Markdown completed",
    }


def test_update_section_phase_checkpoint_writes_outline_json_without_losing_existing_phases() -> (  # noqa: E501
    None
):
    outline = {
        "section_resource_checkpoints": {
            "1.1": {
                "markdown": {
                    "status": "completed",
                    "updated_at": "2026-07-02T00:00:00+00:00",
                    "output_refs": {"section_markdown_id": "1.1"},
                    "quality_result": {"passed": True},
                }
            }
        }
    }

    updated = update_section_phase_checkpoint(
        outline,
        section_id="1.1",
        phase="video",
        status="unavailable",
        output_refs={"video_brief_ids": ["video_1"]},
        quality_result={
            "passed": False,
            "severity": "informational",
            "reason": "未找到合格视频",
        },
        failure_reason="未找到合格视频",
        updated_at="2026-07-02T01:00:00+00:00",
    )

    assert updated is not outline
    assert section_phase_completed(updated, "1.1", "markdown") is True
    assert checkpoint_for_phase(updated, "1.1", "video") == {
        "status": "unavailable",
        "updated_at": "2026-07-02T01:00:00+00:00",
        "output_refs": {"video_brief_ids": ["video_1"]},
        "quality_result": {
            "passed": False,
            "severity": "informational",
            "reason": "未找到合格视频",
        },
        "failure_reason": "未找到合格视频",
    }


def test_trace_builder_records_compact_summaries_without_full_content() -> None:
    trace = build_agent_trace(
        trace_id="session-1:year_3_course_1:1.1:animation",
        agent="section_html_animation_agent",
        phase="animation",
        started_at_ms=1000,
        ended_at_ms=2450,
        input_summary={
            "course_id": "year_3_course_1",
            "section_id": "1.1",
            "source_textbook_id": "textbook-data-structures",
            "brief_ids": ["anim_1"],
            "simulation_type": "data_structure_linked_list",
            "evidence_text": "教材完整正文不应进入 trace",
        },
        output_summary={
            "status": "available",
            "html": "<section>完整 HTML 不应进入 trace</section>",
            "html_length": 12840,
            "quality_passed": True,
        },
        failure_reason="",
    )

    assert trace == {
        "trace_id": "session-1:year_3_course_1:1.1:animation",
        "agent": "section_html_animation_agent",
        "phase": "animation",
        "duration_ms": 1450,
        "input_summary": {
            "course_id": "year_3_course_1",
            "section_id": "1.1",
            "source_textbook_id": "textbook-data-structures",
            "brief_ids": ["anim_1"],
            "simulation_type": "data_structure_linked_list",
        },
        "output_summary": {
            "status": "available",
            "html_length": 12840,
            "quality_passed": True,
        },
        "failure_reason": "",
    }
