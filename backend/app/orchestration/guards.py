from __future__ import annotations

from typing import Any

from app.orchestration.contracts import ContractError, blocking_quality


def _clean_text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _clean_text(item))]


def require_profile_for_intake(state: dict[str, Any]) -> None:
    profile = state.get("profile")
    if not isinstance(profile, dict):
        _raise_profile_error()
    confirmed_info = profile.get("confirmed_info")
    if (
        profile.get("type") != "basic_profile"
        or not isinstance(confirmed_info, dict)
        or not confirmed_info
    ):
        _raise_profile_error()


def require_confirmed_intake_for_learning_path(state: dict[str, Any]) -> None:
    intake = state.get("learning_path_intake")
    if isinstance(intake, dict) and intake.get("status") == "confirmed":
        return
    reason = "learning_path_intake.status is not confirmed"
    raise ContractError(
        "learning_path_agent",
        "path",
        reason,
        blocking_quality(reason),
    )


def require_course_source_for_course_knowledge(course: dict[str, Any]) -> None:
    if _clean_text(course.get("source_textbook_id")) and _text_list(
        course.get("source_outline_section_ids")
    ):
        return
    reason = "course source binding is incomplete"
    raise ContractError(
        "course_knowledge_agent",
        "outline",
        reason,
        blocking_quality(reason),
    )


def require_section_source_for_markdown(section: dict[str, Any]) -> None:
    if _clean_text(section.get("source_textbook_id")) and _text_list(
        section.get("source_section_ids")
    ):
        return
    reason = "section source binding is incomplete"
    raise ContractError(
        "section_markdown_agent",
        "markdown",
        reason,
        blocking_quality(reason),
    )


def _raise_profile_error() -> None:
    reason = "profile is not complete"
    raise ContractError(
        "learning_path_intake_agent",
        "intake",
        reason,
        blocking_quality(reason),
    )
