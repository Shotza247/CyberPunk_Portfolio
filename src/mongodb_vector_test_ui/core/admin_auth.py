from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from mongodb_vector_test_ui.core.config import Settings

PASSWORD_HASH_ITERATIONS = 310_000
PASSWORD_HASH_SCHEME = "pbkdf2_sha256"
TOKEN_ISSUER = "cyberpunk-portfolio-admin"


@dataclass(frozen=True)
class AdminIdentity:
    username: str
    email: str


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if len(password) < 12:
        raise ValueError("Admin password must contain at least 12 characters.")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS, dklen=32
    )
    return "$".join(
        (
            PASSWORD_HASH_SCHEME,
            str(PASSWORD_HASH_ITERATIONS),
            _b64encode(salt),
            _b64encode(digest),
        )
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        scheme, iterations_text, salt_text, digest_text = encoded_hash.split("$", maxsplit=3)
        iterations = int(iterations_text)
        salt = _b64decode(salt_text)
        expected = _b64decode(digest_text)
    except (AttributeError, TypeError, ValueError):
        return False

    if (
        scheme != PASSWORD_HASH_SCHEME
        or iterations < 100_000
        or iterations > 1_000_000
        or len(salt) < 16
        or len(expected) != 32
    ):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations, dklen=len(expected)
    )
    return hmac.compare_digest(actual, expected)


def authenticate_admin(
    username: str, email: str, password: str, settings: Settings
) -> AdminIdentity | None:
    configured = bool(
        settings.admin_username
        and settings.admin_email
        and settings.admin_password_hash
        and len(settings.admin_auth_secret) >= 32
    )
    password_matches = verify_password(password, settings.admin_password_hash)
    username_matches = hmac.compare_digest(
        username.strip().casefold().encode("utf-8"),
        settings.admin_username.strip().casefold().encode("utf-8"),
    )
    email_matches = hmac.compare_digest(
        email.strip().casefold().encode("utf-8"), settings.admin_email.casefold().encode("utf-8")
    )

    if not (configured and password_matches and username_matches and email_matches):
        return None
    return AdminIdentity(username=settings.admin_username, email=settings.admin_email)


def create_access_token(identity: AdminIdentity, settings: Settings) -> str:
    if len(settings.admin_auth_secret) < 32:
        raise ValueError("ADMIN_AUTH_SECRET must contain at least 32 characters.")

    now = int(time.time())
    payload = {
        "iss": TOKEN_ISSUER,
        "sub": identity.username,
        "email": identity.email,
        "iat": now,
        "exp": now + settings.admin_session_ttl_seconds,
        "jti": secrets.token_urlsafe(16),
    }
    encoded_payload = _b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(
        settings.admin_auth_secret.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_b64encode(signature)}"


def verify_access_token(token: str, settings: Settings) -> AdminIdentity | None:
    if len(settings.admin_auth_secret) < 32:
        return None
    try:
        encoded_payload, encoded_signature = token.split(".", maxsplit=1)
        signature = _b64decode(encoded_signature)
        expected = hmac.new(
            settings.admin_auth_secret.encode("utf-8"),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(signature, expected):
            return None

        payload = json.loads(_b64decode(encoded_payload))
        if (
            payload.get("iss") != TOKEN_ISSUER
            or not isinstance(payload.get("sub"), str)
            or not isinstance(payload.get("email"), str)
            or not isinstance(payload.get("exp"), int)
            or payload["exp"] <= int(time.time())
        ):
            return None
        return AdminIdentity(username=payload["sub"], email=payload["email"])
    except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
