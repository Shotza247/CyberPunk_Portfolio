from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from mongodb_vector_test_ui.api import admin as admin_module
from mongodb_vector_test_ui.api import fastapi as fastapi_module
from mongodb_vector_test_ui.api import operations
from mongodb_vector_test_ui.api.fastapi import app
from mongodb_vector_test_ui.core import metrics as metrics_module
from mongodb_vector_test_ui.core.admin_auth import hash_password
from mongodb_vector_test_ui.core.config import Settings

EXPECTED_ROUTES = {
    ("/", "GET"),
    ("/api/workbench", "GET"),
    ("/api/auth/login", "POST"),
    ("/api/auth/session", "GET"),
    ("/api/badges", "GET"),
    ("/api/metrics", "GET"),
    ("/api/admin/badges", "GET"),
    ("/api/admin/badges", "POST"),
    ("/api/admin/badges/{badge_id}", "DELETE"),
    ("/api/status", "GET"),
    ("/api/mongodb/databases", "GET"),
    ("/api/mongodb/collections", "GET"),
    ("/api/mongodb/collection/summary", "GET"),
    ("/api/index/create", "POST"),
    ("/api/document/extract/upload", "POST"),
    ("/api/document/extract/path", "POST"),
    ("/api/document/chunks", "POST"),
    ("/api/index/document", "POST"),
    ("/api/search", "POST"),
    ("/api/rerank", "POST"),
    ("/api/ask", "POST"),
}


def test_fastapi_is_primary_application() -> None:
    assert isinstance(app, FastAPI)
    assert app.title == "Lex Portfolio Operations API"
    assert isinstance(admin_module.router, APIRouter)
    assert isinstance(operations.router, APIRouter)


def test_fastapi_preserves_mvp1_route_contract() -> None:
    routes = {
        (path, method.upper())
        for path, path_item in app.openapi()["paths"].items()
        for method in path_item
        if method.upper() in {"GET", "POST", "DELETE"}
    }
    routes.update({("/", "GET"), ("/api/workbench", "GET")})

    assert EXPECTED_ROUTES <= routes


def test_fastapi_exposes_openapi_for_api_routes() -> None:
    schema = app.openapi()

    assert "/api/status" in schema["paths"]
    assert "/api/index/document" in schema["paths"]
    assert "/api/search" in schema["paths"]
    assert "/api/rerank" in schema["paths"]
    assert "/api/ask" in schema["paths"]
    assert "/api/auth/login" in schema["paths"]
    assert "/api/admin/badges" in schema["paths"]


def test_browser_ui_uses_lex_profile_agent_simulator() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "LEX // PROFILE AGENT SIMULATOR" in response.text
    assert "fetch(\"/api/ask\"" in response.text
    assert "top_k: 3, min_score: 0.6" in response.text
    assert 'callJson("/api/search"' not in response.text
    assert 'callJson("/api/rerank"' not in response.text
    assert "LIVE // OPERATIONS TELEMETRY" in response.text
    assert "Recent operations" in response.text


def test_admin_page_reuses_floating_profile_chat_widget() -> None:
    admin_html = (Path(__file__).resolve().parents[1] / "admin.html").read_text(
        encoding="utf-8"
    )

    assert 'id="ship-btn"' in admin_html
    assert 'id="chat-panel"' in admin_html
    assert 'id="chat-input"' in admin_html
    assert 'data-q="What is Jabulani' in admin_html
    assert '<link rel="stylesheet" href="styles.css">' in admin_html
    assert '<script src="profile-assistant.js"></script>' in admin_html


def test_profile_chat_checks_health_on_load_and_wake_with_extended_timeouts() -> None:
    assistant_js = (Path(__file__).resolve().parents[1] / "profile-assistant.js").read_text(
        encoding="utf-8"
    )

    assert "const RAG_HEALTH_TIMEOUT_MS = 10000;" in assistant_js
    assert "const RAG_REQUEST_TIMEOUT_MS = 300000;" in assistant_js
    assert "void checkRagHealth().catch(error => {" in assistant_js
    assert "Lex RAG health check failed on page load." in assistant_js
    open_chat = assistant_js.split("function openChat()", 1)[1].split(
        "function closeChat()", 1
    )[0]
    assert "void checkRagHealth()" in open_chat
    assert "RAG /api/ask timed out after ${RAG_REQUEST_TIMEOUT_MS / 1000} seconds." in assistant_js


def test_admin_api_routes_require_bearer_authentication() -> None:
    client = TestClient(app)

    for path in (
        "/api/auth/session",
        "/api/metrics",
        "/api/admin/badges",
        "/api/mongodb/databases",
        "/api/index/create",
        "/api/search",
    ):
        response = client.get(path) if path != "/api/index/create" else client.post(path, json={})
        assert response.status_code == 401


def test_admin_api_cors_preflight_does_not_require_bearer_authentication(monkeypatch) -> None:
    settings = Settings(frontend_origins=("http://localhost:5500",))
    monkeypatch.setattr(fastapi_module, "get_settings", lambda: settings)
    response = TestClient(fastapi_module.create_app()).options(
        "/api/admin/badges",
        headers={
            "Origin": "http://localhost:5500",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5500"
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_owner_can_sign_in_and_manage_public_badges(monkeypatch) -> None:
    settings = Settings(
        admin_username="owner",
        admin_email="owner@example.com",
        admin_password_hash=hash_password("a-long-admin-password"),
        admin_auth_secret="s" * 48,
        frontend_origins=("http://localhost:5500",),
    )
    monkeypatch.setattr(fastapi_module, "get_settings", lambda: settings)
    monkeypatch.setattr(admin_module, "get_settings", lambda: settings)
    badges = []

    class FakeBadgeStore:
        def __init__(self, _settings):
            pass

        def list_badges(self):
            return list(badges)

        def create_badge(self, badge):
            record = {"id": "a" * 32, **badge}
            badges.append(record)
            return record

        def delete_badge(self, badge_id):
            for index, badge in enumerate(badges):
                if badge["id"] == badge_id:
                    del badges[index]
                    return True
            return False

    class FakeMetricsStore:
        def __init__(self, _settings):
            pass

        def dashboard(self, window_hours):
            return {"window_hours": window_hours, "operations": {}, "recent": []}

    monkeypatch.setattr(admin_module, "PortfolioBadgeStore", FakeBadgeStore)
    monkeypatch.setattr(admin_module, "OperationMetricsStore", FakeMetricsStore)
    client = TestClient(fastapi_module.create_app())
    login = client.post(
        "/api/auth/login",
        json={
            "username": "owner",
            "email": "owner@example.com",
            "password": "a-long-admin-password",
        },
    )

    assert login.status_code == 200
    headers = {
        "Authorization": f"Bearer {login.json()['access_token']}",
        "Origin": "http://localhost:5500",
    }
    metrics = client.get("/api/metrics?window_hours=6", headers=headers)
    assert metrics.status_code == 200
    assert metrics.json()["window_hours"] == 6
    assert "x-operation-metrics" in metrics.headers["access-control-expose-headers"].lower()
    badge = {
        "title": "Cloud Foundations",
        "issuer": "Example Academy",
        "description": "Cloud fundamentals",
        "url": "https://credentials.example.com/cloud",
    }

    created = client.post("/api/admin/badges", json=badge, headers=headers)
    assert created.status_code == 201
    assert client.get("/api/badges").json()["badges"] == [created.json()["badge"]]
    removed = client.delete(
        f"/api/admin/badges/{created.json()['badge']['id']}", headers=headers
    )
    assert removed.status_code == 200
    assert client.get("/api/badges").json()["badges"] == []


def test_lex_chat_simulator_uses_ask_and_returns_user_facing_citations(monkeypatch) -> None:
    settings = Settings(frontend_origins=("http://localhost:5500",))
    records = []

    class FakeMetricsStore:
        def __init__(self, _settings):
            pass

        def record(self, metric):
            records.append(metric)

    class FakeVectorStore:
        def __init__(self, _settings):
            pass

        def vector_index_filter_paths(self):
            return set()

        def vector_search(self, *_args, **_kwargs):
            return [
                {
                    "source_id": "profile",
                    "chunk_id": "profile-chunk-1",
                    "text": "Jabulani develops data and AI engineering solutions.",
                    "score": 0.84,
                    "metadata": {"title": "Career Profile", "section": "Experience"},
                }
            ]

    monkeypatch.setattr(fastapi_module, "get_settings", lambda: settings)
    monkeypatch.setattr(operations, "get_settings", lambda: settings)
    monkeypatch.setattr(metrics_module, "get_settings", lambda: settings)
    monkeypatch.setattr(metrics_module, "OperationMetricsStore", FakeMetricsStore)
    monkeypatch.setattr(operations, "MongoVectorStore", FakeVectorStore)
    monkeypatch.setattr(operations, "embed_query", lambda *_args: [0.1, 0.2])
    monkeypatch.setattr(
        operations,
        "synthesize_answer",
        lambda *_args, **_kwargs: {
            "answer": "Jabulani works across data and AI [E1].",
            "citations": [
                {
                    "evidence_id": "E1",
                    "source_id": "profile",
                    "chunk_id": "profile-chunk-1",
                    "title": "Career Profile",
                    "section": "Experience",
                    "vector_score": 0.84,
                    "rerank_score": 0.93,
                }
            ],
            "insufficient_evidence": False,
            "candidate_count": 1,
            "reranked_count": 1,
            "evidence_count": 1,
            "stage_timings_ms": {"reranking": 2.5, "answer_generation": 8.2},
        },
    )
    monkeypatch.setattr(
        operations, "safe_model_diagnostics", lambda: {"chat_provider": "openai", "chat_model": "gpt-5.5"}
    )
    monkeypatch.setattr(
        operations,
        "safe_reranker_diagnostics",
        lambda _settings: {"rerank_provider": "voyage", "rerank_model": "rerank-2.5"},
    )

    response = TestClient(fastapi_module.create_app()).post(
        "/api/ask",
        json={"query": "What does Jabulani do?", "top_k": 3, "min_score": 0.6},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chat_model"] == "gpt-5.5"
    assert payload["answer"].endswith("[E1].")
    assert payload["citations"][0]["title"] == "Career Profile"
    assert payload["timings_ms"]["rerank"] == 2.5
    assert payload["timings_ms"]["answer_generation"] == 8.2
    assert records[0]["operation"] == "query"
