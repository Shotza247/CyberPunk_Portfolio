from __future__ import annotations

import json
import logging
import math
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from functools import wraps
from time import perf_counter
from typing import Any

from fastapi import Request
from fastapi.responses import Response
from pymongo import DESCENDING, MongoClient

from mongodb_vector_test_ui.core.config import Settings, get_settings

OPERATIONS = ("query", "retrieval", "reranking", "indexing")
TOKEN_ESTIMATION_METHOD = "estimated_4_characters_per_token"
logger = logging.getLogger(__name__)


def instrument_operation(
    endpoint: Callable[[Request], Awaitable[Response]], operation: str
) -> Callable[[Request], Awaitable[Response]]:
    @wraps(endpoint)
    async def measured(request: Request) -> Response:
        started = perf_counter()
        request.state.operation_stages_ms = {}
        request.state.operation_payload = {}
        response: Response | None = None
        status_code = 500
        try:
            response = await endpoint(request)
            status_code = response.status_code
            return response
        finally:
            elapsed_ms = (perf_counter() - started) * 1000
            try:
                settings = get_settings()
                payload = request.state.operation_payload
                metric = build_operation_metric(
                    operation=operation,
                    payload=payload,
                    response_body=response.body if response is not None else b"",
                    status_code=status_code,
                    latency_ms=elapsed_ms,
                    stages_ms=request.state.operation_stages_ms,
                    settings=settings,
                    target_database=str(payload.get("mongodb_db", settings.mongodb_db)),
                    target_collection=str(
                        payload.get("mongodb_collection", settings.mongodb_collection)
                    ),
                )
                OperationMetricsStore(settings).record(metric)
                if response is not None:
                    response.headers["X-Operation-Metrics"] = "stored"
            except Exception:
                logger.exception("Could not persist %s operation metrics.", operation)
                if response is not None:
                    response.headers["X-Operation-Metrics"] = "write-failed"

    return measured


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 4) if text else 0


def build_operation_metric(
    *,
    operation: str,
    payload: dict[str, Any],
    response_body: bytes,
    status_code: int,
    latency_ms: float,
    stages_ms: dict[str, float],
    settings: Settings,
    target_database: str | None = None,
    target_collection: str | None = None,
) -> dict[str, Any]:
    request_text = _request_text(operation, payload)
    response_text = _response_text(response_body)
    response_data = _json_object(response_body)
    result_count = _first_integer(
        response_data,
        "result_count",
        "candidate_count",
        "inserted",
        "chunks_created",
    )
    return {
        "timestamp": datetime.now(UTC),
        "operation": operation,
        "status_code": status_code,
        "success": status_code < 400,
        "latency_ms": round(latency_ms, 2),
        "stages_ms": {name: round(value, 2) for name, value in stages_ms.items()},
        "input_tokens_est": estimate_tokens(request_text),
        "output_tokens_est": estimate_tokens(response_text),
        "token_estimation_method": TOKEN_ESTIMATION_METHOD,
        "result_count": result_count,
        "mongodb_db": target_database or settings.mongodb_db,
        "mongodb_collection": target_collection or settings.mongodb_collection,
    }


class OperationMetricsStore:
    def __init__(self, settings: Settings) -> None:
        if not settings.mongodb_uri:
            raise ValueError("MONGODB_URI is required to store operation metrics.")
        if not settings.metrics_collection or "\x00" in settings.metrics_collection:
            raise ValueError("METRICS_COLLECTION must be a non-empty MongoDB collection name.")
        if settings.metrics_collection.startswith("system."):
            raise ValueError("METRICS_COLLECTION cannot use the MongoDB system. namespace.")
        if settings.metrics_collection in {
            settings.mongodb_collection,
            settings.badge_collection,
        }:
            raise ValueError("METRICS_COLLECTION must be separate from the vector and badge collections.")
        self.settings = settings
        self.client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=3000)
        self.collection = self.client[settings.mongodb_db][settings.metrics_collection]

    def record(self, metric: dict[str, Any]) -> None:
        try:
            self.collection.insert_one(metric)
        finally:
            self.client.close()

    def dashboard(self, window_hours: int = 24, limit: int = 500) -> dict[str, Any]:
        try:
            self.collection.create_index([("timestamp", DESCENDING)])
            records = list(
                self.collection.find(
                    {"timestamp": {"$gte": datetime.now(UTC) - timedelta(hours=window_hours)}},
                    projection={
                        "_id": 0,
                        "operation": 1,
                        "status_code": 1,
                        "success": 1,
                        "latency_ms": 1,
                        "stages_ms": 1,
                        "input_tokens_est": 1,
                        "output_tokens_est": 1,
                        "token_estimation_method": 1,
                        "result_count": 1,
                        "mongodb_db": 1,
                        "mongodb_collection": 1,
                        "timestamp": 1,
                    },
                )
                .sort("timestamp", DESCENDING)
                .limit(limit)
            )
        finally:
            self.client.close()
        return summarize_metrics(records, window_hours=window_hours)


def summarize_metrics(records: list[dict[str, Any]], *, window_hours: int) -> dict[str, Any]:
    operations: dict[str, dict[str, Any]] = {}
    for operation in OPERATIONS:
        matching = [record for record in records if record.get("operation") == operation]
        latencies = sorted(
            float(record.get("latency_ms", 0))
            for record in matching
            if isinstance(record.get("latency_ms"), int | float)
        )
        p95_index = max(0, math.ceil(len(latencies) * 0.95) - 1) if latencies else 0
        operations[operation] = {
            "count": len(matching),
            "failures": sum(not record.get("success", False) for record in matching),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
            "p95_latency_ms": round(latencies[p95_index], 2) if latencies else 0,
            "max_latency_ms": round(latencies[-1], 2) if latencies else 0,
            "input_tokens_est": sum(int(record.get("input_tokens_est", 0)) for record in matching),
            "output_tokens_est": sum(int(record.get("output_tokens_est", 0)) for record in matching),
            "result_count": sum(int(record.get("result_count", 0)) for record in matching),
        }

    recent = [
        {
            key: _serializable_value(value)
            for key, value in record.items()
            if key
            in {
                "timestamp",
                "operation",
                "status_code",
                "success",
                "latency_ms",
                "stages_ms",
                "input_tokens_est",
                "output_tokens_est",
                "result_count",
                "mongodb_db",
                "mongodb_collection",
            }
        }
        for record in records[:50]
    ]
    return {
        "window_hours": window_hours,
        "sample_limit": 500,
        "record_count": len(records),
        "token_counts_are_estimates": True,
        "token_estimation_method": TOKEN_ESTIMATION_METHOD,
        "operations": operations,
        "recent": recent,
    }


def _request_text(operation: str, payload: dict[str, Any]) -> str:
    if operation == "indexing":
        return str(payload.get("text", ""))
    if operation == "reranking":
        candidates = payload.get("candidates")
        candidate_text = (
            " ".join(str(item.get("text", "")) for item in candidates if isinstance(item, dict))
            if isinstance(candidates, list)
            else ""
        )
        return f"{payload.get('question', payload.get('query', ''))} {candidate_text}"
    return str(payload.get("query", payload.get("question", "")))


def _response_text(body: bytes) -> str:
    data = _json_object(body)
    parts: list[str] = []
    answer = data.get("answer")
    if isinstance(answer, str):
        parts.append(answer)
    for item in data.get("results", []):
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return " ".join(parts)


def _json_object(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _first_integer(data: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = data.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return max(value, 0)
    return 0


def _serializable_value(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def record_request_stage(request: Any, name: str, started_at: float) -> None:
    stages = getattr(request.state, "operation_stages_ms", None)
    if stages is not None:
        stages[name] = (perf_counter() - started_at) * 1000


@contextmanager
def measure_request_stage(request: Any, name: str) -> Iterator[None]:
    started_at = perf_counter()
    try:
        yield
    finally:
        record_request_stage(request, name, started_at)
