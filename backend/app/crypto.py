"""Encryption for vendor credentials stored in the database.

The key lives only in the environment (CREDENTIALS_KEY), never in the database or the repo, so a
database backup alone contains no usable secrets. Several comma-separated keys are accepted for
rotation: the first encrypts, all can decrypt (see docs/INTEGRATIONS.md).
"""

import json

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import get_settings


class CredentialsKeyError(RuntimeError):
    """The key is missing or unusable; the message never contains key material."""


def _fernet() -> MultiFernet:
    raw = [k.strip() for k in get_settings().credentials_key.split(",") if k.strip()]
    if not raw:
        raise CredentialsKeyError("CREDENTIALS_KEY is not set; see docs/INTEGRATIONS.md")
    try:
        return MultiFernet([Fernet(k.encode()) for k in raw])
    except (ValueError, TypeError) as exc:
        raise CredentialsKeyError("CREDENTIALS_KEY is not a valid Fernet key") from exc


def encrypt_credentials(values: dict[str, str]) -> str:
    return _fernet().encrypt(json.dumps(values).encode()).decode()


def decrypt_credentials(token: str) -> dict[str, str]:
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except InvalidToken as exc:
        raise CredentialsKeyError(
            "stored credentials cannot be decrypted with the configured key"
        ) from exc


def reencrypt(token: str) -> str:
    """Re-encrypt with the primary key (used by the key-rotation job)."""
    return _fernet().rotate(token.encode()).decode()
