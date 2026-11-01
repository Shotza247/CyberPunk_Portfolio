from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mongodb_vector_test_ui.api import admin, operations
from mongodb_vector_test_ui.core.admin_auth import verify_access_token
from mongodb_vector_test_ui.core.config import get_settings, validated_frontend_origins


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Lex Portfolio Operations API",
        summary="MongoDB Vector Search and profile assistant operations",
        description=(
            "Protected portfolio operations, vector retrieval, indexing, and performance telemetry."
        ),
        version="0.2.0",
        debug=settings.app_env == "local",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=validated_frontend_origins(settings),
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Operation-Metrics"],
        allow_credentials=False,
        max_age=600,
    )

    protected_paths = {
        "/api/auth/session",
        "/api/metrics",
        "/api/status",
        "/api/mongodb/databases",
        "/api/mongodb/collections",
        "/api/mongodb/collection/summary",
        "/api/index/create",
        "/api/document/extract/upload",
        "/api/document/extract/path",
        "/api/document/chunks",
        "/api/index/document",
        "/api/search",
        "/api/rerank",
    }

    @app.middleware("http")
    async def require_admin(request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        identity = (
            verify_access_token(token, get_settings())
            if scheme.casefold() == "bearer" and token
            else None
        )

        if path == "/api/status":
            if authorization and identity is None:
                return JSONResponse({"error": "Admin session is invalid."}, status_code=401)
            if identity is not None:
                request.state.admin_identity = identity
            return await call_next(request)

        if path not in protected_paths and not path.startswith("/api/admin/"):
            return await call_next(request)

        if identity is None:
            return JSONResponse({"error": "Admin sign-in is required."}, status_code=401)

        request.state.admin_identity = identity
        return await call_next(request)

    app.include_router(operations.router)
    app.add_api_route(
        "/api/workbench",
        operations.home,
        methods=["GET"],
        summary="Authenticated Lex operations dashboard",
        tags=["operations"],
        include_in_schema=False,
    )
    app.include_router(admin.router)

    return app


app = create_app()
