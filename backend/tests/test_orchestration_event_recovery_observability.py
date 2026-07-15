from __future__ import annotations

import asyncio

import pytest

import app.orchestration.agents.course_resources as course_resources_pkg
from app.orchestration.agents.course_resources.main import (
    stream_chapter_resource_generation,
)
from app.orchestration.contracts import quality_passed
from app.orchestration.events import build_agent_event
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


def test_update_section_phase_checkpoint_preserves_existing_phases() -> None:
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


def test_stream_chapter_resource_generation_uses_unified_events_and_checkpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "数据结构",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "线性表",
            },
            {
                "section_id": "1.1",
                "parent_section_id": "1",
                "depth": 2,
                "title": "单链表",
                "source_textbook_id": "textbook-data-structures",
                "source_section_ids": ["2.3"],
            },
        ],
    }
    state = {
        "session_id": "session-1",
        "user_id": "user-1",
        "course_knowledge": outline,
    }

    async def fake_markdown_agent(state_arg, _llm, _args):
        updated_outline = dict(state_arg["course_knowledge"])
        updated_outline["section_markdowns"] = {
            "1.1": {
                "section_id": "1.1",
                "source_references": [{"textbook_id": "textbook-data-structures"}],
                "video_briefs": [{"video_id": "video_1"}],
                "animation_briefs": [{"animation_id": "anim_1"}],
            }
        }
        return {
            "course_knowledge": updated_outline,
            "course_resource_plan": {"target_section_ids": ["1.1"]},
        }

    async def fake_video_agent(state_arg, _llm):
        updated_outline = dict(state_arg["course_knowledge"])
        updated_outline["section_video_links"] = {
            "1.1": {
                "videos": [],
                "unavailable_videos": [
                    {"brief_id": "video_1", "failure_reason": "未找到合格视频"}
                ],
            }
        }
        existing_plan = state_arg.get("course_resource_plan") or {}
        updated_plan = dict(existing_plan) if isinstance(existing_plan, dict) else {}
        updated_plan["video_unavailable_section_ids"] = ["1.1"]
        return {
            "course_knowledge": updated_outline,
            "course_resource_plan": updated_plan,
        }

    async def fake_animation_agent(state_arg, _llm):
        updated_outline = dict(state_arg["course_knowledge"])
        updated_outline["section_html_animations"] = {
            "1.1": {"animations": [{"animation_id": "anim_1", "html": "<div />"}]}
        }
        updated_outline["section_composed_markdowns"] = {
            "1.1": {
                "blocks": [{"type": "markdown"}],
                "source_references": [{"textbook_id": "textbook-data-structures"}],
            }
        }
        return {"course_knowledge": updated_outline}

    monkeypatch.setattr(
        course_resources_pkg,
        "run_section_markdown_agent",
        fake_markdown_agent,
    )
    monkeypatch.setattr(
        course_resources_pkg,
        "run_section_video_search_agent",
        fake_video_agent,
    )
    monkeypatch.setattr(
        course_resources_pkg,
        "run_section_html_animation_agent",
        fake_animation_agent,
    )

    async def collect_events() -> list[dict]:
        return [
            event
            async for event in stream_chapter_resource_generation(
                state,
                object(),
                object(),
                course_id="year_3_course_1",
                chapter_section_id="1",
            )
        ]

    events = asyncio.run(collect_events())

    agent_events = [event for event in events if event["event"].startswith("agent_")]
    assert all("agent_order" in event for event in agent_events)
    assert all("depends_on" in event for event in agent_events)
    assert all("input_refs" in event for event in agent_events)
    assert all("output_refs" in event for event in agent_events)
    result_phases = [
        event["phase"] for event in agent_events if event["event"] == "agent_result"
    ]
    assert result_phases == [
        "markdown",
        "video",
        "animation",
        "compose",
    ]

    checkpoints = state["course_knowledge"]["section_resource_checkpoints"]["1.1"]
    assert checkpoints["markdown"]["status"] == "completed"
    assert checkpoints["video"]["output_refs"]["unavailable_video_count"] == 1
    assert checkpoints["animation"]["output_refs"]["animation_count"] == 1
    assert checkpoints["compose"]["output_refs"]["source_reference_count"] == 1
