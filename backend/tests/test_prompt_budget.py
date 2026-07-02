from __future__ import annotations

from app.orchestration.prompt_budget import (
    PHASE_PROMPT_LIMITS,
    apply_prompt_budget,
)


def test_phase_prompt_limits_match_resource_contract() -> None:
    assert PHASE_PROMPT_LIMITS == {
        "intake": 8000,
        "path": 12000,
        "outline": 16000,
        "markdown": 28000,
        "video": 9000,
        "animation": 12000,
    }


def test_apply_prompt_budget_preserves_current_source_binding() -> None:
    prompt = "A" * 200 + "\nSOURCE_BINDING:textbook-ai-web:2.3\n" + "B" * 200

    result = apply_prompt_budget(
        prompt,
        phase="video",
        protected_fragments=["SOURCE_BINDING:textbook-ai-web:2.3"],
        limit=120,
    )

    assert result.prompt_budget_applied is True
    assert "SOURCE_BINDING:textbook-ai-web:2.3" in result.text
    assert len(result.text) <= 120


def test_apply_prompt_budget_does_not_trim_when_under_limit() -> None:
    result = apply_prompt_budget("short prompt", phase="intake")

    assert result.prompt_budget_applied is False
    assert result.text == "short prompt"
