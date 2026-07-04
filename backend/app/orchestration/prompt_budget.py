from __future__ import annotations

from dataclasses import dataclass

from app.orchestration.contracts import PhaseName

PHASE_PROMPT_LIMITS: dict[str, int] = {
    "intake": 8000,
    "path": 12000,
    "outline": 16000,
    "markdown": 28000,
    "video": 9000,
    "animation": 12000,
}


@dataclass(frozen=True)
class PromptBudgetResult:
    text: str
    prompt_budget_applied: bool
    original_chars: int
    final_chars: int


def apply_prompt_budget(
    text: str,
    *,
    phase: PhaseName,
    protected_fragments: list[str] | None = None,
    limit: int | None = None,
) -> PromptBudgetResult:
    prompt_limit = limit or PHASE_PROMPT_LIMITS.get(phase, 12000)
    if len(text) <= prompt_limit:
        return PromptBudgetResult(
            text=text,
            prompt_budget_applied=False,
            original_chars=len(text),
            final_chars=len(text),
        )

    protected = [fragment for fragment in protected_fragments or [] if fragment]
    protected_text = "\n".join(protected)
    remaining_limit = max(0, prompt_limit - len(protected_text) - 2)
    head = text[: remaining_limit // 2]
    tail = text[-(remaining_limit - len(head)) :] if remaining_limit > len(head) else ""
    trimmed = f"{head}\n{protected_text}\n{tail}".strip()
    if len(trimmed) > prompt_limit:
        trimmed = trimmed[:prompt_limit]
        for fragment in protected:
            if fragment in trimmed:
                continue
            prefix_limit = max(0, prompt_limit - len(fragment) - 1)
            trimmed = f"{trimmed[:prefix_limit]}\n{fragment}"[:prompt_limit]
    return PromptBudgetResult(
        text=trimmed,
        prompt_budget_applied=True,
        original_chars=len(text),
        final_chars=len(trimmed),
    )
