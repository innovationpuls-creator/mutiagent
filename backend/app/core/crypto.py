"""Application-layer encryption for user-owned model credentials."""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

DEV_ENCRYPTION_KEY = "mutiagent-dev-model-secret-key-change-in-production"


class SecretKeyUnavailableError(RuntimeError):
    """Raised when credentials must be (de)crypted but no key is configured."""


class SecretDecryptError(RuntimeError):
    """Raised when stored ciphertext cannot be decrypted with the current key."""


class SecretCipher:
    """Fernet wrapper; any non-empty key string is stretched with SHA-256."""

    def __init__(self, key: str | None) -> None:
        self._fernet: Fernet | None = None
        if key:
            digest = hashlib.sha256(key.encode("utf-8")).digest()
            self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    @property
    def available(self) -> bool:
        return self._fernet is not None

    def _require(self) -> Fernet:
        if self._fernet is None:
            raise SecretKeyUnavailableError("MODEL_SECRET_ENCRYPTION_KEY 未配置")
        return self._fernet

    def encrypt(self, plaintext: str) -> str:
        return self._require().encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._require().decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise SecretDecryptError("凭据无法解密，请重新保存") from exc


def build_cipher(key: str | None, *, is_production: bool) -> SecretCipher:
    if key:
        return SecretCipher(key)
    if is_production:
        logger.error("MODEL_SECRET_ENCRYPTION_KEY 未配置：个人模型凭据功能不可用")
        return SecretCipher(None)
    logger.warning("MODEL_SECRET_ENCRYPTION_KEY 未配置，开发环境使用默认加密密钥")
    return SecretCipher(DEV_ENCRYPTION_KEY)


def mask_secret(secret: str | None) -> str | None:
    """Keep only the last four characters; never reveal short secrets."""
    if not secret:
        return None
    if len(secret) <= 8:
        return "••••"
    return f"••••{secret[-4:]}"
