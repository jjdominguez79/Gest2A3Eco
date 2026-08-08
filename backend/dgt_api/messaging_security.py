from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_password(value: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(value.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=64)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(value: str, stored: str) -> bool:
    try:
        prefix, n, r, p, salt, expected = stored.split("$", 5)
        if prefix != "scrypt":
            return False
        digest = hashlib.scrypt(
            value.encode("utf-8"), salt=bytes.fromhex(salt),
            n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(expected)),
        )
        return hmac.compare_digest(digest, bytes.fromhex(expected))
    except Exception:
        return False


def invitation_expiry() -> datetime:
    return utcnow() + timedelta(hours=72)


def session_expiry() -> datetime:
    return utcnow() + timedelta(days=30)


def is_expired(value: datetime | None) -> bool:
    if value is None:
        return True
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= utcnow()
