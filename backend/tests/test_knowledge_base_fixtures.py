from __future__ import annotations

from tests.fixtures.knowledge_base import (
    archived_textbook,
    continuous_sections,
    enabled_source,
    extension_resources_four,
    extension_resources_three,
    followed_gap_student,
    non_continuous_sections,
    over_8000_char_sections,
    published_textbook,
    uncovered_topic_gap,
    unenabled_source,
    unpublished_textbook,
)


def test_source_and_textbook_samples_cover_contract_statuses() -> None:
    assert enabled_source().status == "enabled"
    assert unenabled_source().status == "disabled"
    assert published_textbook().student_availability_status == "published"
    assert unpublished_textbook().student_availability_status == "draft"
    assert archived_textbook().student_availability_status == "archived"


def test_section_samples_cover_continuity_and_length_contracts() -> None:
    continuous_indexes = [section.order_index for section in continuous_sections()]
    assert continuous_indexes == list(
        range(continuous_indexes[0], continuous_indexes[-1] + 1)
    )

    non_continuous_indexes = [
        section.order_index for section in non_continuous_sections()
    ]
    assert non_continuous_indexes != list(
        range(non_continuous_indexes[0], non_continuous_indexes[-1] + 1)
    )

    over_limit_sections = over_8000_char_sections()
    assert sum(len(section.content_zh) for section in over_limit_sections) > 8000
    assert all(
        section.content_char_count == len(section.content_zh)
        for section in over_limit_sections
    )


def test_gap_follow_and_extension_resource_samples_cover_counts() -> None:
    gap = uncovered_topic_gap()
    follow = followed_gap_student()

    assert gap.status == "open"
    assert gap.normalized_topic
    assert follow.gap_id == gap.gap_id
    assert follow.user_uid
    assert len(extension_resources_three()) == 3
    assert len(extension_resources_four()) == 4
