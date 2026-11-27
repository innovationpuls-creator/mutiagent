from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

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


def quality_passed() -> QualityResult:
    return QualityResult(passed=True, severity="informational", reason="")
