from mongodb_vector_test_ui.core.admin_auth import (
    AdminIdentity,
    authenticate_admin,
    create_access_token,
    hash_password,
    verify_access_token,
    verify_password,
)
from mongodb_vector_test_ui.core.config import Settings


def test_password_hash_verifies_only_the_original_password() -> None:
    encoded = hash_password("a-long-admin-password")

    assert verify_password("a-long-admin-password", encoded)
    assert not verify_password("incorrect-password", encoded)
    assert not verify_password("a-long-admin-password", "invalid-hash")


def test_admin_requires_username_email_and_password() -> None:
    settings = Settings(
        admin_username="owner",
        admin_email="owner@example.com",
        admin_password_hash=hash_password("a-long-admin-password"),
        admin_auth_secret="s" * 48,
    )

    assert authenticate_admin("owner", "owner@example.com", "a-long-admin-password", settings)
    assert authenticate_admin("OWNER", "OWNER@example.com", "a-long-admin-password", settings)
    assert authenticate_admin("owner", "wrong@example.com", "a-long-admin-password", settings) is None
    assert authenticate_admin("owner", "owner@example.com", "wrong-password", settings) is None


def test_access_token_is_signed_and_expires() -> None:
    settings = Settings(admin_auth_secret="s" * 48)
    identity = AdminIdentity(username="owner", email="owner@example.com")
    token = create_access_token(identity, settings)

    assert verify_access_token(token, settings) == identity
    assert verify_access_token(f"{token}x", settings) is None
    assert verify_access_token(token, Settings(admin_auth_secret="t" * 48)) is None


def test_short_admin_password_is_rejected() -> None:
    try:
        hash_password("short")
    except ValueError as exc:
        assert "12 characters" in str(exc)
    else:
        raise AssertionError("Expected password length validation to fail.")
