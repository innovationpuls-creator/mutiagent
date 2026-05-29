from __future__ import annotations

from hashlib import sha256
from secrets import token_urlsafe


PASSWORD_NAMESPACE = "mutiagent-auth"


def hash_password(password: str) -> str:
    return sha256(f"{PASSWORD_NAMESPACE}:{password}".encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False

    return hash_password(password) == password_hash


def create_mock_token() -> str:
    return f"mock-token-{token_urlsafe(24)}"
