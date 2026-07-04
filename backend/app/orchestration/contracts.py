from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

AgentName = Literal[
    "profile_agent",
    "learning_path_intake_agent",
    "learning_path_agent",
    "course_knowledge_agent",
    "section_markdown_agent",
    "section_video_search_agent",
    "section_html_animation_agent",
    "compose_resource",
]

PhaseName = Literal[
    "profile",
    "intake",
    "path",
    "outline",
    "markdown",
    "video",
    "animation",
    "compose",
]

Severity = Literal["blocking", "recoverable", "informational"]
ResourceStatus = Literal[
    "available",
    "unavailable",
    "recoverable_failed",
    "blocking_failed",
]

AGENT_ORDER: dict[AgentName, int] = {
    "profile_agent": 1,
    "learning_path_intake_agent": 2,
    "learning_path_agent": 3,
    "course_knowledge_agent": 4,
    "section_markdown_agent": 5,
    "section_video_search_agent": 6,
    "section_html_animation_agent": 7,
    "compose_resource": 8,
}


@dataclass(frozen=True)
class QualityCheck:
    name: str
    passed: bool
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "reason": self.reason}


@dataclass(frozen=True)
class QualityResult:
    passed: bool
    severity: Severity
    reason: str = ""
    checks: list[QualityCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "severity": self.severity,
            "reason": self.reason,
            "checks": [check.to_dict() for check in self.checks],
        }


class ContractError(ValueError):
    def __init__(
        self,
        agent: AgentName,
        phase: PhaseName,
        message: str,
        quality_result: QualityResult | None = None,
    ) -> None:
        super().__init__(f"{agent}:{phase}:{message}")
        self.agent = agent
        self.phase = phase
        self.quality_result = quality_result or QualityResult(
            passed=False,
            severity="blocking",
            reason=message,
        )


def agent_order(agent: AgentName) -> int:
    return AGENT_ORDER[agent]


def quality_passed() -> QualityResult:
    return QualityResult(passed=True, severity="informational", reason="")


def blocking_quality(
    reason: str, checks: list[QualityCheck] | None = None
) -> QualityResult:
    return QualityResult(
        passed=False,
        severity="blocking",
        reason=reason,
        checks=checks or [],
    )


def recoverable_quality(
    reason: str, checks: list[QualityCheck] | None = None
) -> QualityResult:
    return QualityResult(
        passed=False,
        severity="recoverable",
        reason=reason,
        checks=checks or [],
    )
