from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from mongodb_vector_test_ui.core.admin_auth import (
    authenticate_admin,
    create_access_token,
)
from mongodb_vector_test_ui.core.config import get_settings
from mongodb_vector_test_ui.core.metrics import OperationMetricsStore
from mongodb_vector_test_ui.vectorstore.badges import PortfolioBadgeStore

BADGE_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
logger = logging.getLogger(__name__)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("username", "email")
    @classmethod
    def strip_identity(cls, value: str) -> str:
        return value.strip()

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("A valid email address is required.")
        return value


class BadgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    issuer: str = Field(default="Independent credential", max_length=80)
    description: str = Field(default="", max_length=280)
    url: str = Field(min_length=1, max_length=2048)

    @field_validator("title", "issuer", "description", "url")
    @classmethod
    def strip_strings(cls, value: str) -> str:
        return value.strip()

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        if not value:
            raise ValueError("A badge title is required.")
        return value

    @field_validator("url")
    @classmethod
    def require_safe_https_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Credential links must be valid HTTPS URLs.")
        return value


async def login(request: Request) -> JSONResponse:
    settings = get_settings()
    if not (
        settings.admin_username
        and settings.admin_email
        and settings.admin_password_hash
        and len(settings.admin_auth_secret) >= 32
    ):
        return JSONResponse(
            {"error": "Admin authentication is not configured on the server."},
            status_code=503,
        )

    try:
        payload = LoginRequest.model_validate(await request.json())
    except (ValidationError, ValueError):
        return JSONResponse({"error": "Enter a valid username, email, and password."}, status_code=422)

    identity = authenticate_admin(
        payload.username, payload.email, payload.password, settings
    )
    if identity is None:
        return JSONResponse({"error": "Invalid username, email, or password."}, status_code=401)

    return JSONResponse(
        {
            "access_token": create_access_token(identity, settings),
            "token_type": "bearer",
            "expires_in": settings.admin_session_ttl_seconds,
            "username": identity.username,
            "email": identity.email,
        }
    )


async def session(request: Request) -> JSONResponse:
    identity = request.state.admin_identity
    return JSONResponse({"username": identity.username, "email": identity.email})


async def public_badges(request: Request) -> JSONResponse:
    try:
        badges = PortfolioBadgeStore(get_settings()).list_badges()
        return JSONResponse({"badges": badges})
    except Exception:
        logger.exception("Could not load public portfolio badges.")
        return JSONResponse({"error": "Portfolio badges are temporarily unavailable."}, status_code=503)


async def admin_badges(request: Request) -> JSONResponse:
    try:
        badges = PortfolioBadgeStore(get_settings()).list_badges()
        return JSONResponse({"badges": badges})
    except Exception:
        logger.exception("Could not load admin portfolio badges.")
        return JSONResponse({"error": "Portfolio badges are temporarily unavailable."}, status_code=503)


async def create_badge(request: Request) -> JSONResponse:
    try:
        payload = BadgeRequest.model_validate(await request.json())
    except (ValidationError, ValueError):
        return JSONResponse({"error": "Provide a valid title and HTTPS credential URL."}, status_code=422)

    try:
        badge = PortfolioBadgeStore(get_settings()).create_badge(payload.model_dump())
        return JSONResponse({"badge": badge}, status_code=201)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    except Exception:
        logger.exception("Could not save a portfolio badge.")
        return JSONResponse({"error": "Portfolio badge could not be saved."}, status_code=503)


async def delete_badge(request: Request) -> JSONResponse:
    badge_id = request.path_params.get("badge_id", "")
    if not BADGE_ID_PATTERN.fullmatch(badge_id):
        return JSONResponse({"error": "Badge ID is invalid."}, status_code=422)

    try:
        deleted = PortfolioBadgeStore(get_settings()).delete_badge(badge_id)
        if not deleted:
            return JSONResponse({"error": "Badge was not found."}, status_code=404)
        return JSONResponse({"deleted": True})
    except Exception:
        logger.exception("Could not remove a portfolio badge.")
        return JSONResponse({"error": "Portfolio badge could not be removed."}, status_code=503)


async def operation_metrics(request: Request) -> JSONResponse:
    try:
        window_hours = int(request.query_params.get("window_hours", "24"))
    except ValueError:
        return JSONResponse({"error": "window_hours must be 1, 6, 24, or 168."}, status_code=422)
    if window_hours not in {1, 6, 24, 168}:
        return JSONResponse({"error": "window_hours must be 1, 6, 24, or 168."}, status_code=422)

    try:
        dashboard = OperationMetricsStore(get_settings()).dashboard(window_hours=window_hours)
        return JSONResponse(dashboard)
    except Exception:
        logger.exception("Could not load MongoDB operation metrics.")
        return JSONResponse({"error": "Operation metrics are temporarily unavailable."}, status_code=503)


router = APIRouter(tags=["admin"])
router.add_api_route("/api/auth/login", login, methods=["POST"], summary="Admin sign-in")
router.add_api_route("/api/auth/session", session, methods=["GET"], summary="Admin session")
router.add_api_route("/api/badges", public_badges, methods=["GET"], tags=["badges"])
router.add_api_route("/api/metrics", operation_metrics, methods=["GET"], tags=["metrics"])
router.add_api_route(
    "/api/admin/badges", admin_badges, methods=["GET"], tags=["badges"]
)
router.add_api_route(
    "/api/admin/badges", create_badge, methods=["POST"], tags=["badges"]
)
router.add_api_route(
    "/api/admin/badges/{badge_id}",
    delete_badge,
    methods=["DELETE"],
    tags=["badges"],
)
