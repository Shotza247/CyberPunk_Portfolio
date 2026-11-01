from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from mongodb_vector_test_ui.core import metrics as metrics_module
from mongodb_vector_test_ui.core.config import Settings
from mongodb_vector_test_ui.core.metrics import (
    TOKEN_ESTIMATION_METHOD,
    build_operation_metric,
    instrument_operation,
    summarize_metrics,
)


def test_operation_metric_counts_tokens_without_storing_request_content() -> None:
    metric = build_operation_metric(
        operation="retrieval",
        payload={"query": "private portfolio query"},
        response_body=b'{"result_count":2,"results":[{"text":"private retrieved text"}]}',
        status_code=200,
        latency_ms=123.456,
        stages_ms={"query_embedding": 12.2, "vector_retrieval": 80.4},
        settings=Settings(),
    )

    assert metric["input_tokens_est"] > 0
    assert metric["output_tokens_est"] > 0
    assert metric["token_estimation_method"] == TOKEN_ESTIMATION_METHOD
    assert metric["latency_ms"] == 123.46
    assert metric["result_count"] == 2
    assert metric["stages_ms"]["vector_retrieval"] == 80.4
    assert metric["mongodb_db"] == Settings().mongodb_db
    assert metric["mongodb_collection"] == Settings().mongodb_collection
    assert "private" not in str(metric)


def test_operation_metrics_record_selected_target_without_moving_metrics_store() -> None:
    metric = build_operation_metric(
        operation="indexing",
        payload={"text": "a private document body"},
        response_body=b'{"inserted":3}',
        status_code=200,
        latency_ms=20,
        stages_ms={},
        settings=Settings(mongodb_db="central_metrics", mongodb_collection="profile_chunks"),
        target_database="selected_project",
        target_collection="selected_chunks",
    )

    assert metric["mongodb_db"] == "selected_project"
    assert metric["mongodb_collection"] == "selected_chunks"
    assert "private" not in str(metric)


def test_metrics_summary_groups_operations_and_computes_p95() -> None:
    records = [
        {
            "timestamp": datetime.now(UTC),
            "operation": "retrieval",
            "success": True,
            "latency_ms": latency,
            "input_tokens_est": 10,
            "output_tokens_est": 5,
            "result_count": 2,
            "stages_ms": {"vector_retrieval": latency / 2},
        }
        for latency in (10, 20, 100)
    ]
    records.append(
        {
            "operation": "indexing",
            "success": False,
            "latency_ms": 50,
            "input_tokens_est": 25,
            "output_tokens_est": 0,
            "result_count": 0,
            "stages_ms": {},
        }
    )

    dashboard = summarize_metrics(records, window_hours=24)

    assert dashboard["operations"]["retrieval"]["count"] == 3
    assert dashboard["operations"]["retrieval"]["avg_latency_ms"] == 43.33
    assert dashboard["operations"]["retrieval"]["p95_latency_ms"] == 100
    assert dashboard["operations"]["indexing"]["failures"] == 1
    assert len(dashboard["recent"]) == 4
    assert dashboard["token_counts_are_estimates"] is True


def test_instrumented_operation_persists_aggregates_without_raw_text(monkeypatch) -> None:
    recorded = []
    settings = Settings()

    class FakeMetricsStore:
        def __init__(self, _settings):
            pass

        def record(self, metric):
            recorded.append(metric)

    async def endpoint(request: Request) -> JSONResponse:
        request.state.operation_payload = await request.json()
        return JSONResponse(
            {"result_count": 1, "results": [{"text": "private retrieval result"}]}
        )

    monkeypatch.setattr(metrics_module, "get_settings", lambda: settings)
    monkeypatch.setattr(metrics_module, "OperationMetricsStore", FakeMetricsStore)
    app = FastAPI()
    app.add_api_route(
        "/api/search",
        instrument_operation(endpoint, "retrieval"),
        methods=["POST"],
    )

    response = TestClient(app).post(
        "/api/search", json={"query": "private search question"}
    )

    assert response.status_code == 200
    assert response.headers["X-Operation-Metrics"] == "stored"
    assert recorded[0]["operation"] == "retrieval"
    assert recorded[0]["result_count"] == 1
    assert recorded[0]["input_tokens_est"] > 0
    assert "private" not in str(recorded[0])
