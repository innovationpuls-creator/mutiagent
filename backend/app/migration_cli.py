from __future__ import annotations

import os

from sqlalchemy import create_engine

from app.migration_state import assert_schema_at_head, migrate_to_head


def main() -> int:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    engine = create_engine(database_url)
    try:
        migrate_to_head(engine)
        assert_schema_at_head(engine)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
