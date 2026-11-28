"""List saved courses that lack a usable textbook binding (read-only).

Run from backend against the target database:
    DATABASE_URL=... uv run python scripts/audit_course_bindings.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session  # noqa: E402

from app.database import build_engine  # noqa: E402
from app.services.binding_audit import audit_course_bindings  # noqa: E402


def main() -> int:
    engine = build_engine()
    with Session(engine) as session:
        problems = audit_course_bindings(session)
    reasons = Counter(item["reason"] for item in problems)
    users = {item["user_uid"] for item in problems}
    print(
        json.dumps(
            {"courses": len(problems), "users": len(users), "by_reason": reasons},
            ensure_ascii=False,
        )
    )
    for item in problems:
        print(json.dumps(item, ensure_ascii=False))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
