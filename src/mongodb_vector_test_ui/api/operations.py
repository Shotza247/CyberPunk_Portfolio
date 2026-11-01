from __future__ import annotations

import base64
import binascii
import html
import json
from datetime import UTC, datetime
from json import JSONDecodeError

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from mongodb_vector_test_ui.chunking.service import chunk_text
from mongodb_vector_test_ui.core.config import (
    get_settings,
    safe_diagnostics,
    validate_settings,
    with_mongodb_target,
)
from mongodb_vector_test_ui.core.metrics import instrument_operation, measure_request_stage
from mongodb_vector_test_ui.embeddings.providers import embed_documents, embed_query
from mongodb_vector_test_ui.ingestion.documents import (
    SUPPORTED_EXTENSIONS,
    extract_from_bytes,
    extract_from_path,
)
from mongodb_vector_test_ui.llm.answering import synthesize_answer
from mongodb_vector_test_ui.llm.providers import safe_model_diagnostics
from mongodb_vector_test_ui.retrieval.rerankers import (
    create_reranker,
    safe_reranker_diagnostics,
)
from mongodb_vector_test_ui.vectorstore.mongodb import MongoVectorStore


async def home(request: Request) -> HTMLResponse:
    settings = get_settings()
    return HTMLResponse(_render_page(settings))


async def status(request: Request) -> JSONResponse:
    try:
        settings = (
            _target_settings_from_query(request)
            if getattr(request.state, "admin_identity", None)
            else get_settings()
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    payload = {
        "timestamp": _now(),
        "config": _safe_config(settings),
        "config_issues": validate_settings(settings),
        "mongo_ok": False,
        "document_count": None,
        "indexes": [],
        "error": None,
    }
    try:
        store = MongoVectorStore(settings)
        payload["mongo_ok"] = store.ping()
        payload["document_count"] = store.count_documents()
        payload["indexes"] = store.list_vector_indexes()
    except Exception as exc:  # noqa: BLE001 - UI status should return diagnostics, not crash.
        payload["error"] = str(exc)
    return JSONResponse(payload)


async def mongodb_databases(request: Request) -> JSONResponse:
    settings = get_settings()
    try:
        store = MongoVectorStore(settings)
        return JSONResponse({"databases": store.list_databases()})
    except Exception as exc:  # noqa: BLE001 - Surface MongoDB browsing errors in the operations dashboard.
        return JSONResponse({"error": str(exc)}, status_code=500)


async def mongodb_collections(request: Request) -> JSONResponse:
    try:
        settings = _target_settings_from_query(request, require_collection=False)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    try:
        store = MongoVectorStore(settings)
        return JSONResponse(
            {"database": settings.mongodb_db, "collections": store.list_collections(settings.mongodb_db)}
        )
    except Exception as exc:  # noqa: BLE001 - Surface MongoDB browsing errors in the operations dashboard.
        return JSONResponse({"error": str(exc)}, status_code=500)


async def mongodb_collection_summary(request: Request) -> JSONResponse:
    try:
        settings = _target_settings_from_query(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    try:
        store = MongoVectorStore(settings)
        return JSONResponse({"summary": store.collection_summary()})
    except Exception as exc:  # noqa: BLE001 - Surface MongoDB browsing errors in the operations dashboard.
        return JSONResponse({"error": str(exc)}, status_code=500)


async def create_index(request: Request) -> JSONResponse:
    try:
        payload = await _json_or_empty(request)
        request.state.operation_payload = payload
        settings = get_settings()
    except JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON."}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    try:
        with measure_request_stage(request, "index_management"):
            store = MongoVectorStore(settings)
            result = store.ensure_vector_index()
            result["indexes"] = store.list_vector_indexes()
        return JSONResponse(result)
    except Exception as exc:  # noqa: BLE001 - Surface database/index errors in the operations dashboard.
        return JSONResponse({"error": str(exc)}, status_code=500)


async def extract_uploaded_document(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON."}, status_code=400)

    filename = str(payload.get("filename", "")).strip()
    encoded = str(payload.get("content_base64", "")).strip()
    if not filename:
        return JSONResponse({"error": "filename is required."}, status_code=422)
    if not encoded:
        return JSONResponse({"error": "content_base64 is required."}, status_code=422)

    try:
        data = base64.b64decode(encoded, validate=True)
        document = extract_from_bytes(data, filename=filename)
        return JSONResponse({"document": document.to_dict()})
    except (binascii.Error, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    except Exception as exc:  # noqa: BLE001 - Surface extraction errors as JSON for the UI.
        return JSONResponse({"error": str(exc)}, status_code=500)


async def extract_path_document(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON."}, status_code=400)

    file_path = str(payload.get("file_path", "")).strip()
    if not file_path:
        return JSONResponse({"error": "file_path is required."}, status_code=422)

    try:
        document = extract_from_path(file_path)
        return JSONResponse({"document": document.to_dict()})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    except Exception as exc:  # noqa: BLE001 - Surface local file extraction errors as JSON.
        return JSONResponse({"error": str(exc)}, status_code=500)


async def preview_chunks(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON."}, status_code=400)

    title = str(payload.get("title", "Test document")).strip() or "Test document"
    source_id = str(payload.get("source_id", "")).strip() or _slug(title)
    text = str(payload.get("text", "")).strip()
    if len(text) < 20:
        return JSONResponse({"error": "Document text must contain at least 20 characters."}, status_code=422)

    chunks = chunk_text(source_id, title, text)
    previews = [
        {
            "chunk_id": chunk["chunk_id"],
            "source_id": chunk["source_id"],
            "metadata": chunk["metadata"],
            "characters": len(chunk["text"]),
            "text": chunk["text"],
        }
        for chunk in chunks
    ]
    return JSONResponse({"source_id": source_id, "title": title, "chunk_count": len(chunks), "chunks": previews})


async def index_document(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON."}, status_code=400)

    request.state.operation_payload = payload
    title = str(payload.get("title", "Test document")).strip() or "Test document"
    source_id = str(payload.get("source_id", "")).strip() or _slug(title)
    text = str(payload.get("text", "")).strip()
    if len(text) < 20:
        return JSONResponse({"error": "Paste at least 20 characters of document text."}, status_code=422)

    try:
        settings = _target_settings_from_payload(payload)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    try:
        with measure_request_stage(request, "chunking"):
            chunks = chunk_text(source_id, title, text)
        with measure_request_stage(request, "embedding"):
            vectors = embed_documents([chunk["text"] for chunk in chunks], settings)
        with measure_request_stage(request, "mongo_write"):
            store = MongoVectorStore(settings)
            inserted = store.replace_source_chunks(source_id, chunks, vectors)
        with measure_request_stage(request, "index_management"):
            index_result = store.ensure_vector_index()
        return JSONResponse(
            {
                "source_id": source_id,
                "title": title,
                "chunks_created": len(chunks),
                "embeddings_created": len(vectors),
                "inserted": inserted,
                "embedding_provider": settings.embedding_provider,
                "embedding_model": _embedding_model(settings),
                "mongodb_db": settings.mongodb_db,
                "mongodb_collection": settings.mongodb_collection,
                "vector_index": settings.vector_index_name,
                "index_result": index_result,
            }
        )
    except Exception as exc:  # noqa: BLE001 - Surface embedding/database errors in the operations dashboard.
        return JSONResponse({"error": str(exc)}, status_code=500)


async def search(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON."}, status_code=400)

    request.state.operation_payload = payload
    query = str(payload.get("query", "")).strip()
    top_k = _top_k(payload.get("top_k", 5))
    min_score = _min_score(payload.get("min_score", 0.6))
    exact = _bool(payload.get("exact", False))
    num_candidates = _num_candidates(payload.get("num_candidates"), top_k=top_k, exact=exact)
    filters = _search_filters(payload)
    if len(query) < 2:
        return JSONResponse({"error": "Query must be at least 2 characters."}, status_code=422)

    try:
        settings = _target_settings_from_payload(payload)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    try:
        with measure_request_stage(request, "query_embedding"):
            query_vector = embed_query(query, settings)
        with measure_request_stage(request, "vector_retrieval"):
            store = MongoVectorStore(settings)
            available_filter_paths = store.vector_index_filter_paths()
            unsupported_filters = sorted(set(filters) - available_filter_paths)
            if unsupported_filters:
                return JSONResponse(
                    {
                        "error": "Selected filter fields are not available on this vector index. Run Create / Check Index to inspect missing filter paths, then update or recreate the Atlas vector index if needed.",
                        "unsupported_filter_paths": unsupported_filters,
                        "available_filter_paths": sorted(available_filter_paths),
                        "filters": filters,
                        "mongodb_db": settings.mongodb_db,
                        "mongodb_collection": settings.mongodb_collection,
                        "vector_index": settings.vector_index_name,
                    },
                    status_code=422,
                )
            results = store.vector_search(
                query_vector,
                top_k=top_k,
                min_score=min_score,
                num_candidates=num_candidates,
                exact=exact,
                filters=filters,
            )
        return JSONResponse(
            {
                "query": query,
                "top_k": top_k,
                "min_score": min_score,
                "num_candidates": num_candidates,
                "exact": exact,
                "filters": filters,
                "embedding_provider": settings.embedding_provider,
                "embedding_model": _embedding_model(settings),
                "mongodb_db": settings.mongodb_db,
                "mongodb_collection": settings.mongodb_collection,
                "result_count": len(results),
                "results": results,
            }
        )
    except Exception as exc:  # noqa: BLE001 - Surface embedding/database errors in the operations dashboard.
        return JSONResponse({"error": str(exc)}, status_code=500)


async def rerank(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON."}, status_code=400)

    request.state.operation_payload = payload
    question = str(payload.get("question") or payload.get("query") or "").strip()
    candidates = payload.get("candidates")
    if len(question) < 2:
        return JSONResponse({"error": "Question must be at least 2 characters."}, status_code=422)
    if not isinstance(candidates, list) or not candidates:
        return JSONResponse({"error": "Candidates must be a non-empty list."}, status_code=422)
    if len(candidates) > 1000:
        return JSONResponse({"error": "Candidates cannot exceed 1000 items."}, status_code=422)
    if any(not isinstance(candidate, dict) for candidate in candidates):
        return JSONResponse({"error": "Every candidate must be a JSON object."}, status_code=422)

    try:
        with measure_request_stage(request, "reranking"):
            results = create_reranker().rerank(question, candidates, top_k=None)
        diagnostics = safe_reranker_diagnostics()
        return JSONResponse(
            {
                "question": question,
                "candidate_count": len(candidates),
                "result_count": len(results),
                "return_all": True,
                "rerank_provider": diagnostics["rerank_provider"],
                "rerank_model": diagnostics["rerank_model"],
                "results": results,
            }
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    except Exception as exc:  # noqa: BLE001 - Surface provider errors in the operations dashboard.
        return JSONResponse({"error": str(exc)}, status_code=500)


async def ask(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON."}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Request body must be a JSON object."}, status_code=400)

    request.state.operation_payload = payload
    query = str(payload.get("query", "")).strip()
    if len(query) < 2:
        return JSONResponse({"error": "Query must be at least 2 characters."}, status_code=422)
    try:
        settings = get_settings()
        top_k = _top_k(payload.get("top_k", 10))
        min_score = _min_score(payload.get("min_score", 0.6))
        exact = _bool(payload.get("exact", False))
        num_candidates = _num_candidates(payload.get("num_candidates"), top_k, exact)
        filters = _search_filters(payload)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    try:
        with measure_request_stage(request, "query_embedding"):
            query_vector = embed_query(query, settings)
        with measure_request_stage(request, "vector_retrieval"):
            store = MongoVectorStore(settings)
            available_paths = store.vector_index_filter_paths()
            unsupported = sorted(set(filters) - available_paths)
            if unsupported:
                return JSONResponse(
                    {
                        "error": "Selected filters are not available on the active vector index.",
                        "available_filter_paths": sorted(available_paths),
                    },
                    status_code=422,
                )
            candidates = store.vector_search(
                query_vector, top_k=top_k, min_score=min_score,
                num_candidates=num_candidates, exact=exact, filters=filters,
            )
    except Exception as exc:  # noqa: BLE001 - Keep retrieval failures in the API contract.
        return JSONResponse({"error": str(exc)}, status_code=500)

    if not candidates:
        model_info = safe_model_diagnostics()
        return JSONResponse(
            {
                "query": query,
                "answer": "The indexed sources do not contain enough information to answer this question.",
                "citations": [], "insufficient_evidence": True,
                "candidate_count": 0, "reranked_count": 0, "evidence_count": 0,
                "results": [], "evidence": [],
                "chat_provider": model_info.get("chat_provider"),
                "chat_model": model_info.get("chat_model"),
                "timings_ms": _ask_timings(request),
                "mongodb_db": settings.mongodb_db,
                "mongodb_collection": settings.mongodb_collection,
            }
        )

    try:
        with measure_request_stage(request, "answer_pipeline"):
            result = synthesize_answer(query, candidates, settings=settings)
        request.state.operation_stages_ms.update(result.get("stage_timings_ms", {}))
        model_info = safe_model_diagnostics()
        rerank_info = safe_reranker_diagnostics(settings)
        return JSONResponse(
            {
                "query": query, **result,
                "embedding_provider": settings.embedding_provider,
                "embedding_model": _embedding_model(settings),
                "rerank_provider": rerank_info["rerank_provider"],
                "rerank_model": rerank_info["rerank_model"],
                "chat_provider": model_info.get("chat_provider"),
                "chat_model": model_info.get("chat_model"),
                "timings_ms": _ask_timings(request),
                "mongodb_db": settings.mongodb_db,
                "mongodb_collection": settings.mongodb_collection,
            }
        )
    except (ValueError, RuntimeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
    except Exception as exc:  # noqa: BLE001 - Surface model-provider failures as JSON.
        return JSONResponse({"error": str(exc)}, status_code=502)


def _safe_config(settings) -> dict:
    diagnostics = safe_diagnostics(settings)
    diagnostics["embedding_model"] = _embedding_model(settings)
    diagnostics.update(safe_model_diagnostics())
    diagnostics.update(safe_reranker_diagnostics(settings))
    return diagnostics


def _ask_timings(request: Request) -> dict[str, float]:
    stages = request.state.operation_stages_ms
    return {
        "embedding": round(stages.get("query_embedding", 0), 2),
        "retrieval": round(stages.get("vector_retrieval", 0), 2),
        "rerank": round(stages.get("reranking", 0), 2),
        "answer_generation": round(stages.get("answer_generation", 0), 2),
    }


async def _json_or_empty(request: Request) -> dict:
    if not (await request.body()):
        return {}
    return await request.json()


def _target_settings_from_query(request: Request, require_collection: bool = True):
    settings = get_settings()
    database = str(request.query_params.get("database", settings.mongodb_db)).strip()
    collection = str(request.query_params.get("collection", settings.mongodb_collection)).strip()
    if not require_collection and not collection:
        collection = settings.mongodb_collection
    return with_mongodb_target(settings, database=database, collection=collection)


def _target_settings_from_payload(payload: dict):
    settings = get_settings()
    database = str(payload.get("mongodb_db", settings.mongodb_db)).strip()
    collection = str(payload.get("mongodb_collection", settings.mongodb_collection)).strip()
    return with_mongodb_target(settings, database=database, collection=collection)


def _embedding_model(settings) -> str:
    if settings.embedding_provider == "voyage":
        return settings.voyage_model
    if settings.embedding_provider == "openai":
        return settings.openai_embedding_model
    return "deterministic hashing"


def _top_k(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 5
    return min(max(parsed, 1), 50)


def _num_candidates(value: object, top_k: int, exact: bool) -> int | None:
    if exact:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = max(get_settings().vector_num_candidates, top_k * 20)
    return min(max(parsed, top_k), 10000)


def _min_score(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 0.6
    return min(max(parsed, 0.0), 1.0)


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _search_filters(payload: dict) -> dict:
    fields = {
        "metadata.source_id": str(payload.get("source_id_filter", "")).strip(),
        "metadata.title": str(payload.get("title_filter", "")).strip(),
        "metadata.section": str(payload.get("section_filter", "")).strip(),
        "chunk_id": str(payload.get("chunk_id_filter", "")).strip(),
    }
    return {field: value for field, value in fields.items() if value}


def _slug(value: str) -> str:
    chars = [c.lower() if c.isalnum() else "-" for c in value]
    return "-".join(part for part in "".join(chars).split("-") if part)[:80] or "test-document"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _render_page(settings) -> str:
    config_json = html.escape(json.dumps(_safe_config(settings), indent=2))
    frontend_origins_json = json.dumps(settings.frontend_origins)
    default_target_json = json.dumps(
        {"mongodb_db": settings.mongodb_db, "mongodb_collection": settings.mongodb_collection}
    )
    supported_extensions = ", ".join(SUPPORTED_EXTENSIONS)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LEX // MONGODB OPERATIONS DECK</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Space+Mono:wght@400;700&family=Rajdhani:wght@400;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #0a0a0f;
      --panel: #111124;
      --panel-2: #0d0d1a;
      --text: #e0e0ff;
      --muted: #8585a8;
      --line: rgba(0,245,255,0.2);
      --cyan: #00f5ff;
      --green: #72f5be;
      --amber: #f5c518;
      --red: #ff2a6d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font: 14px/1.7 'Space Mono', monospace;
      background:
        radial-gradient(ellipse at 12% 0%, rgba(123,47,255,0.13), transparent 38rem),
        radial-gradient(ellipse at 100% 30%, rgba(0,245,255,0.08), transparent 34rem),
        var(--bg);
      color: var(--text);
    }}
    body::before {{
      position: fixed;
      z-index: 20;
      inset: 0;
      background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.08) 2px, rgba(0,0,0,0.08) 4px);
      content: '';
      pointer-events: none;
    }}
    main {{
      width: min(1180px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 48px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      margin-bottom: 20px;
    }}
    h1 {{ margin: 0 0 6px; color: var(--cyan); font: 900 clamp(1.3rem, 3vw, 2rem) 'Orbitron', monospace; letter-spacing: 0.06em; }}
    p {{ color: var(--muted); line-height: 1.55; }}
    code, pre {{ font-family: Consolas, Monaco, monospace; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 0;
      padding: 16px;
      min-width: 0;
    }}
    .wide {{ grid-column: 1 / -1; }}
    .row {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
    .stack {{ display: grid; gap: 10px; }}
    label {{ display: block; color: var(--muted); font-size: 0.82rem; margin-bottom: 6px; }}
    input, textarea, select {{
      width: 100%;
      color: var(--text);
      background: #0b0f15;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 12px;
      outline: none;
    }}
    input[type="file"] {{ display: none; }}
    textarea {{ min-height: 220px; resize: vertical; }}
    button {{
      background: var(--cyan);
      color: #041018;
      border: 0;
      border-radius: 6px;
      padding: 10px 14px;
      font-weight: 700;
      cursor: pointer;
    }}
    button.secondary {{ background: var(--panel-2); color: var(--text); border: 1px solid var(--line); }}
    button:disabled {{ opacity: 0.55; cursor: wait; }}
    .status {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      border-radius: 999px;
      background: var(--panel-2);
      color: var(--muted);
      border: 1px solid var(--line);
      white-space: nowrap;
    }}
    .dot {{ width: 9px; height: 9px; border-radius: 50%; background: var(--amber); }}
    .dot.ok {{ background: var(--green); }}
    .dot.bad {{ background: var(--red); }}
    pre {{
      overflow: auto;
      max-height: 380px;
      background: #0b0f15;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      color: #dce7f8;
      line-height: 1.45;
    }}
    .cards {{ display: grid; gap: 10px; }}
    .result {{
      background: var(--panel-2);
      border: 1px solid var(--line);
      border-left: 3px solid var(--cyan);
      border-radius: 8px;
      padding: 12px;
    }}
    .chat-shell {{ display: grid; grid-template-columns: minmax(0, 1fr) 260px; gap: 16px; margin-top: 16px; }}
    .chat-main {{ display: grid; min-width: 0; grid-template-rows: minmax(320px, 1fr) auto; gap: 12px; }}
    .chat-transcript {{ display: flex; flex-direction: column; gap: 14px; min-height: 320px; max-height: 580px; overflow: auto; padding: 16px; border: 1px solid var(--line); background: rgba(5,5,12,0.7); }}
    .chat-empty {{ align-self: center; margin: auto; color: var(--muted); text-align: center; }}
    .chat-message {{ max-width: min(86%, 760px); padding: 12px 14px; border: 1px solid var(--line); background: var(--panel-2); white-space: pre-wrap; overflow-wrap: anywhere; }}
    .chat-message.user {{ align-self: flex-end; border-color: rgba(123,47,255,0.6); background: rgba(123,47,255,0.12); }}
    .chat-message.assistant {{ align-self: flex-start; }}
    .chat-message.error {{ border-color: var(--red); }}
    .chat-role {{ display: block; margin-bottom: 5px; color: var(--cyan); font: 700 0.65rem 'Orbitron', monospace; letter-spacing: 0.08em; }}
    .chat-message.user .chat-role {{ color: #b59cff; }}
    .chat-answer {{ margin: 0; color: var(--text); white-space: pre-wrap; }}
    .chat-citations {{ display: grid; gap: 8px; margin-top: 12px; }}
    .chat-citation {{ padding: 9px 10px; border-left: 2px solid var(--violet); background: rgba(123,47,255,0.08); color: var(--muted); font-size: 0.72rem; overflow-wrap: anywhere; }}
    .chat-citation strong {{ color: var(--cyan); }}
    .chat-composer {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: end; }}
    .chat-composer textarea {{ min-height: 74px; max-height: 180px; }}
    .chat-side {{ display: flex; flex-direction: column; gap: 12px; }}
    .chat-side .metric-card {{ flex: 1; }}
    .chat-health[data-state="success"] {{ color: var(--green); }}
    .chat-health[data-state="error"] {{ color: var(--red); }}
    .chat-health[data-state="loading"] {{ color: var(--amber); }}
    .chat-indicators {{ display: grid; gap: 8px; margin: 12px 0 0; }}
    .chat-indicators span {{ display: flex; justify-content: space-between; gap: 8px; color: var(--muted); font-size: 0.69rem; }}
    .chat-indicators strong {{ color: var(--text); font-weight: 400; }}
    .chat-config {{ display: grid; gap: 10px; }}
    .chat-config select {{ width: 100%; }}
    .chat-thinking {{ align-self: flex-start; color: var(--amber); font-size: 0.72rem; }}
    .score {{ color: var(--green); font-weight: 700; }}
    .muted {{ color: var(--muted); }}
    .target {{
      display: inline-flex;
      gap: 6px;
      align-items: center;
      color: var(--muted);
      font-size: 0.86rem;
    }}
    .target strong {{ color: var(--text); }}
    .check {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .check input {{ width: auto; }}
    .dropzone {{
      display: grid;
      place-items: center;
      min-height: 116px;
      padding: 16px;
      background: #0b0f15;
      border: 1px dashed var(--line);
      border-radius: 8px;
      color: var(--muted);
      text-align: center;
      cursor: pointer;
    }}
    .dropzone.dragover {{
      border-color: var(--cyan);
      color: var(--text);
      background: rgba(57, 213, 255, 0.08);
    }}
    .mini {{
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 0.82rem;
    }}
    .metrics-header {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }}
    .metrics-header h2, .metrics-stage-heading {{ margin: 0; color: var(--cyan); font-family: 'Orbitron', monospace; font-size: 0.95rem; }}
    .metrics-controls select {{ width: auto; min-width: 120px; }}
    .metrics-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 16px; }}
    .metric-card {{ min-width: 0; padding: 14px; border: 1px solid var(--line); background: var(--panel-2); }}
    .metric-card h3 {{ margin: 0 0 10px; color: var(--text); font: 700 0.8rem 'Orbitron', monospace; text-transform: uppercase; }}
    .metric-card strong {{ display: block; color: var(--cyan); font-size: 1.35rem; line-height: 1.35; }}
    .metric-card .mini {{ font-size: 0.72rem; }}
    .metrics-lower {{ display: grid; grid-template-columns: minmax(220px, 0.8fr) minmax(0, 1.2fr); gap: 16px; margin-top: 16px; }}
    .stage-list {{ display: grid; gap: 10px; margin-top: 12px; }}
    .stage-row {{ display: grid; grid-template-columns: minmax(80px, 0.65fr) minmax(90px, 1fr) 64px; align-items: center; gap: 10px; color: var(--muted); font-size: 0.72rem; }}
    .latency-track {{ height: 8px; overflow: hidden; background: rgba(224,224,255,0.08); }}
    .latency-track span {{ display: block; height: 100%; background: linear-gradient(90deg, var(--violet), var(--cyan)); }}
    .table-wrap {{ overflow-x: auto; margin-top: 12px; }}
    .metrics-table {{ width: 100%; border-collapse: collapse; font-size: 0.72rem; text-align: left; }}
    .metrics-table th, .metrics-table td {{ padding: 8px 10px; border-bottom: 1px solid rgba(0,245,255,0.12); white-space: nowrap; }}
    .metrics-table th {{ color: var(--cyan); font-weight: 700; }}
    .metrics-table td {{ color: var(--muted); }}
    .metrics-ok {{ color: var(--green) !important; }}
    .metrics-error {{ color: var(--red) !important; }}
    .metrics-note {{ margin-top: 14px; }}
    @media (max-width: 820px) {{
      header, .grid, .metrics-lower, .chat-shell {{ grid-template-columns: 1fr; display: grid; }}
      .metrics-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 460px) {{ .metrics-grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>LEX // MONGODB OPERATIONS DECK</h1>
      <p>Operate the portfolio's MongoDB vector index, ingestion pipeline, retrieval, reranking, and Lex assistant from one workspace.</p>
    </div>
    <div class="status"><span id="status-dot" class="dot"></span><span id="status-text">Checking MongoDB</span></div>
  </header>
  <p id="admin-access-status" class="mini" role="status" aria-live="polite">Waiting for the signed-in portfolio admin session.</p>

  <section class="panel wide" aria-labelledby="metrics-title">
    <div class="metrics-header">
      <div>
        <h2 id="metrics-title">LIVE // OPERATIONS TELEMETRY</h2>
        <p class="mini">Query, retrieval, reranking, and indexing performance recorded in MongoDB.</p>
      </div>
      <div class="row metrics-controls">
        <label for="metrics-window">Time window</label>
        <select id="metrics-window">
          <option value="1">Last hour</option>
          <option value="6">Last 6 hours</option>
          <option value="24" selected>Last 24 hours</option>
          <option value="168">Last 7 days</option>
        </select>
        <button id="refresh-metrics" class="secondary">Refresh Metrics</button>
      </div>
    </div>
    <p id="metrics-status" class="mini" role="status" aria-live="polite">Sign in to load operation telemetry.</p>
    <div class="metrics-grid">
      <article class="metric-card" data-operation="query">
        <h3>Query / Lex</h3>
        <strong class="metric-count">0 runs</strong>
        <p class="mini">Avg <span class="metric-average">0 ms</span> · P95 <span class="metric-p95">0 ms</span> · Max <span class="metric-max">0 ms</span></p>
        <p class="mini">Estimated tokens <span class="metric-tokens">0 in / 0 out</span></p>
        <p class="mini">Results <span class="metric-results">0</span></p>
      </article>
      <article class="metric-card" data-operation="retrieval">
        <h3>Vector retrieval</h3>
        <strong class="metric-count">0 runs</strong>
        <p class="mini">Avg <span class="metric-average">0 ms</span> · P95 <span class="metric-p95">0 ms</span> · Max <span class="metric-max">0 ms</span></p>
        <p class="mini">Estimated tokens <span class="metric-tokens">0 in / 0 out</span></p>
        <p class="mini">Results <span class="metric-results">0</span></p>
      </article>
      <article class="metric-card" data-operation="reranking">
        <h3>Reranking</h3>
        <strong class="metric-count">0 runs</strong>
        <p class="mini">Avg <span class="metric-average">0 ms</span> · P95 <span class="metric-p95">0 ms</span> · Max <span class="metric-max">0 ms</span></p>
        <p class="mini">Estimated tokens <span class="metric-tokens">0 in / 0 out</span></p>
        <p class="mini">Results <span class="metric-results">0</span></p>
      </article>
      <article class="metric-card" data-operation="indexing">
        <h3>Indexing</h3>
        <strong class="metric-count">0 runs</strong>
        <p class="mini">Avg <span class="metric-average">0 ms</span> · P95 <span class="metric-p95">0 ms</span> · Max <span class="metric-max">0 ms</span></p>
        <p class="mini">Estimated tokens <span class="metric-tokens">0 in / 0 out</span></p>
        <p class="mini">Results <span class="metric-results">0</span></p>
      </article>
    </div>
    <div class="metrics-lower">
      <div class="metric-card">
        <h3 class="metrics-stage-heading">Stage latency // recent sample</h3>
        <div id="metrics-stages" class="stage-list"><p class="mini">No stage timings recorded yet.</p></div>
      </div>
      <div class="metric-card">
        <h3 class="metrics-stage-heading">Recent operations</h3>
        <div class="table-wrap">
          <table class="metrics-table">
            <thead><tr><th>Operation</th><th>Result</th><th>Latency</th><th>Tokens est.</th><th>Stages</th></tr></thead>
            <tbody id="metrics-recent"><tr><td colspan="5">No operations recorded yet.</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>
    <p class="mini metrics-note">Token counts are rough estimates (~4 characters/token), not provider billing usage. Request text is not stored; metrics contain timings, counts, status, and database target only.</p>
  </section>

  <section class="grid">
    <div class="panel">
      <h2>Runtime Config</h2>
      <pre id="config">{config_json}</pre>
      <div class="row">
        <button id="refresh" class="secondary">Refresh Status</button>
        <button id="create-index">Create / Check Index</button>
      </div>
    </div>

    <div class="panel">
      <h2>Status</h2>
      <pre id="status-output">Waiting...</pre>
    </div>

    <div class="panel wide">
      <h2>MongoDB Browser</h2>
      <p class="mini">Inspect an available database and collection without editing server configuration.</p>
      <div class="grid">
        <div>
          <label for="database-select">Database</label>
          <select id="database-select">
            <option value="{html.escape(settings.mongodb_db)}">{html.escape(settings.mongodb_db)}</option>
          </select>
        </div>
        <div>
          <label for="collection-select">Collection</label>
          <select id="collection-select">
            <option value="{html.escape(settings.mongodb_collection)}">{html.escape(settings.mongodb_collection)}</option>
          </select>
        </div>
      </div>
      <div class="row">
        <button id="load-databases" class="secondary">Load Databases</button>
        <button id="load-collections" class="secondary">Load Collections</button>
        <button id="inspect-collection">Inspect Collection</button>
        <span class="target">Active target: <strong id="active-target">{html.escape(settings.mongodb_db)}.{html.escape(settings.mongodb_collection)}</strong></span>
      </div>
      <pre id="browser-output">No database browser run yet.</pre>
    </div>

    <div class="panel wide">
      <h2>Document Ingestion</h2>
      <div class="grid">
        <div class="stack">
          <div>
            <label for="file-path">Local File Path</label>
            <input id="file-path" placeholder="C:\\path\\to\\document.pdf">
          </div>
          <div class="row">
            <button id="load-path" class="secondary">Extract From Path</button>
          </div>
        </div>
        <div class="stack">
          <label for="file-input">Upload Or Drop</label>
          <div id="dropzone" class="dropzone" role="button" tabindex="0">
            <span>Drop TXT, PDF, DOCX or choose file</span>
          </div>
          <input id="file-input" type="file" accept="{supported_extensions}">
          <p class="mini">Supported: {html.escape(supported_extensions)}</p>
        </div>
      </div>
      <pre id="extract-output">No document extracted yet.</pre>
    </div>

    <div class="panel wide">
      <h2>Review, Chunk, Embed, Store</h2>
      <div class="grid">
        <div>
          <label for="title">Title</label>
          <input id="title" value="Profile Agent Knowledge Source">
        </div>
        <div>
          <label for="source-id">Source ID</label>
          <input id="source-id" value="profile-agent-knowledge">
        </div>
      </div>
      <label for="doc-text">Document Text</label>
      <textarea id="doc-text">Jabulani is building a Profile Agent that uses MongoDB Vector Search and Voyage embeddings. The assistant should answer questions about his data engineering, AI systems, analytics projects, and portfolio work using retrieved source context.</textarea>
      <div class="row">
        <button id="preview-chunks" class="secondary">Preview Chunks</button>
        <button id="index-doc">Chunk, Embed, and Store</button>
      </div>
      <pre id="chunk-output">No chunk preview yet.</pre>
      <pre id="index-output">No indexing run yet.</pre>
    </div>

    <section class="panel wide" aria-labelledby="lex-chat-title">
      <div class="metrics-header">
        <div>
          <h2 id="lex-chat-title">LEX // PROFILE AGENT SIMULATOR</h2>
          <p class="mini">Test the same grounded `/api/ask` experience used by portfolio visitors: ask naturally, then inspect the answer, citations, and timings.</p>
        </div>
        <div class="row">
          <span id="chat-health" class="chat-health mini" role="status" aria-live="polite">Checking Lex API readiness…</span>
          <button id="new-chat" class="secondary" type="button">New Conversation</button>
        </div>
      </div>
      <div class="chat-shell">
        <div class="chat-main">
          <div id="chat-transcript" class="chat-transcript" role="log" aria-live="polite" aria-label="Lex conversation">
            <p id="chat-empty" class="chat-empty">LEX // ONLINE<br>Ask about Jabulani's experience, projects, skills, or certifications.</p>
          </div>
          <form id="chat-form" class="chat-composer">
            <div>
              <label for="chat-query">Your question</label>
              <textarea id="chat-query" name="query" maxlength="2000" rows="2" required placeholder="Ask Lex a question as a portfolio visitor…"></textarea>
            </div>
            <button id="chat-send" type="submit">ASK LEX ↗</button>
          </form>
        </div>
        <aside class="chat-side" aria-label="Lex request diagnostics">
          <div class="metric-card">
            <h3 class="metrics-stage-heading">Request profile</h3>
            <p class="mini">This simulator sends the public assistant's defaults.</p>
            <div class="chat-indicators">
              <span>Endpoint <strong>POST /api/ask</strong></span>
              <span>Top K <strong>3</strong></span>
              <span>Minimum score <strong>0.60</strong></span>
              <span>Required model <strong>gpt-5.5</strong></span>
            </div>
          </div>
          <div class="metric-card">
            <h3 class="metrics-stage-heading">Latest response</h3>
            <div class="chat-indicators">
              <span>Health check <strong id="chat-health-latency">—</strong></span>
              <span>Client elapsed <strong id="chat-client-latency">—</strong></span>
              <span>Embedding <strong id="chat-embedding-latency">—</strong></span>
              <span>Retrieval <strong id="chat-retrieval-latency">—</strong></span>
              <span>Reranking <strong id="chat-rerank-latency">—</strong></span>
              <span>Answer generation <strong id="chat-generation-latency">—</strong></span>
              <span>Evidence chunks <strong id="chat-evidence-count">—</strong></span>
            </div>
          </div>
        </aside>
      </div>
      <p class="mini metrics-note">Queries use the live profile index. Successful and failed `/api/ask` calls are included in the MongoDB operations telemetry.</p>
    </section>
  </section>
</main>
<script>
const $ = (id) => document.getElementById(id);
const defaultTarget = {default_target_json};
const trustedOrigins = new Set({frontend_origins_json});
let adminAccessToken = "";
let metricsRefreshInterval = null;

window.addEventListener("message", (event) => {{
  if (!trustedOrigins.has(event.origin) || !event.data || typeof event.data !== "object") return;
  if (event.data.type === "portfolio-admin-session" && typeof event.data.accessToken === "string") {{
    adminAccessToken = event.data.accessToken;
    $("admin-access-status").textContent = "LEX ADMIN // AUTHORIZED SESSION ACTIVE";
    refreshStatus();
    refreshMetrics();
    clearInterval(metricsRefreshInterval);
    metricsRefreshInterval = setInterval(refreshMetrics, 30000);
  }}
  if (event.data.type === "portfolio-admin-logout") {{
    adminAccessToken = "";
    clearInterval(metricsRefreshInterval);
    metricsRefreshInterval = null;
    $("admin-access-status").textContent = "Signed out. Reopen this workbench from the portfolio admin.";
  }}
}});

async function callJson(url, options = {{}}) {{
  const headers = {{ "Content-Type": "application/json", ...(options.headers || {{}}) }};
  if (adminAccessToken) headers.Authorization = `Bearer ${{adminAccessToken}}`;
  const response = await fetch(url, {{
    ...options,
    headers
  }});
  const data = await response.json();
  if (response.ok && response.headers.get("X-Operation-Metrics") === "write-failed") {{
    const metricsStatus = $("metrics-status");
    metricsStatus.textContent = "Operation completed, but its telemetry could not be saved to MongoDB.";
    metricsStatus.className = "mini metrics-error";
  }}
  if (!response.ok) {{
    if (response.status === 401 && adminAccessToken) {{
      adminAccessToken = "";
      $("admin-access-status").textContent = "Admin session expired. Sign in again.";
      for (const origin of trustedOrigins) {{
        window.parent.postMessage({{ type: "portfolio-admin-session-expired" }}, origin);
      }}
    }}
    throw new Error(data.error || data.detail || JSON.stringify(data));
  }}
  return data;
}}

function pretty(value) {{
  return JSON.stringify(value, null, 2);
}}

function setBusy(button, busy) {{
  button.disabled = busy;
}}

async function refreshStatus() {{
  try {{
    const data = await callJson(`/api/status?${{targetQuery()}}`);
    $("status-output").textContent = pretty(data);
    $("status-dot").className = "dot " + (data.mongo_ok ? "ok" : "bad");
    $("status-text").textContent = data.mongo_ok ? `MongoDB OK - ${{data.document_count}} docs` : "MongoDB issue";
  }} catch (error) {{
    $("status-output").textContent = String(error);
    $("status-dot").className = "dot bad";
    $("status-text").textContent = "Status failed";
  }}
}}

async function refreshMetrics() {{
  const status = $("metrics-status");
  status.textContent = "Loading MongoDB operation telemetry…";
  status.className = "mini";
  try {{
    const windowHours = $("metrics-window").value;
    const data = await callJson(`/api/metrics?window_hours=${{encodeURIComponent(windowHours)}}`);
    renderMetrics(data);
    status.textContent = `${{data.record_count}} operations · last ${{data.window_hours}}h · sample capped at ${{data.sample_limit}}`;
    status.className = "mini metrics-ok";
  }} catch (error) {{
    status.textContent = `Telemetry unavailable: ${{error.message}}`;
    status.className = "mini metrics-error";
  }}
}}

function renderMetrics(data) {{
  for (const [operation, stats] of Object.entries(data.operations || {{}})) {{
    const card = document.querySelector(`[data-operation="${{operation}}"]`);
    if (!card) continue;
    card.querySelector(".metric-count").textContent = `${{stats.count}} runs · ${{stats.failures}} failed`;
    card.querySelector(".metric-average").textContent = `${{stats.avg_latency_ms}} ms`;
    card.querySelector(".metric-p95").textContent = `${{stats.p95_latency_ms}} ms`;
    card.querySelector(".metric-max").textContent = `${{stats.max_latency_ms}} ms`;
    card.querySelector(".metric-tokens").textContent =
      `${{stats.input_tokens_est.toLocaleString()}} in / ${{stats.output_tokens_est.toLocaleString()}} out`;
    card.querySelector(".metric-results").textContent = stats.result_count.toLocaleString();
  }}

  const stageValues = new Map();
  for (const record of data.recent || []) {{
    for (const [stage, duration] of Object.entries(record.stages_ms || {{}})) {{
      if (!Number.isFinite(duration)) continue;
      const current = stageValues.get(stage) || {{ total: 0, count: 0 }};
      current.total += duration;
      current.count += 1;
      stageValues.set(stage, current);
    }}
  }}
  const stages = [...stageValues.entries()]
    .map(([name, value]) => ({{ name, average: value.total / value.count }}))
    .sort((left, right) => right.average - left.average);
  const stageList = $("metrics-stages");
  stageList.replaceChildren();
  if (!stages.length) {{
    stageList.appendChild(Object.assign(document.createElement("p"), {{
      className: "mini",
      textContent: "No stage timings recorded yet."
    }}));
  }} else {{
    const maximum = Math.max(...stages.map((stage) => stage.average), 1);
    for (const stage of stages) {{
      const row = document.createElement("div");
      row.className = "stage-row";
      const name = document.createElement("span");
      name.textContent = stage.name.replaceAll("_", " ");
      const track = document.createElement("div");
      track.className = "latency-track";
      const fill = document.createElement("span");
      fill.style.width = `${{Math.min(100, stage.average / maximum * 100)}}%`;
      track.appendChild(fill);
      const duration = document.createElement("strong");
      duration.textContent = `${{stage.average.toFixed(1)}} ms`;
      row.append(name, track, duration);
      stageList.appendChild(row);
    }}
  }}

  const recent = $("metrics-recent");
  recent.replaceChildren();
  if (!(data.recent || []).length) {{
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.textContent = "No operations recorded yet.";
    row.appendChild(cell);
    recent.appendChild(row);
    return;
  }}
  for (const record of data.recent) {{
    const row = document.createElement("tr");
    const values = [
      record.operation || "unknown",
      record.success ? `OK · ${{record.status_code}}` : `ERROR · ${{record.status_code}}`,
      `${{record.latency_ms}} ms`,
      `${{(record.input_tokens_est || 0).toLocaleString()}} / ${{(record.output_tokens_est || 0).toLocaleString()}}`,
      Object.entries(record.stages_ms || {{}})
        .map(([name, duration]) => `${{name}} ${{duration}}ms`)
        .join(" · ") || "—"
    ];
    for (let index = 0; index < values.length; index += 1) {{
      const cell = document.createElement("td");
      cell.textContent = values[index];
      if (index === 1) cell.className = record.success ? "metrics-ok" : "metrics-error";
      row.appendChild(cell);
    }}
    recent.appendChild(row);
  }}
}}

async function loadDatabases() {{
  const button = $("load-databases");
  setBusy(button, true);
  try {{
    const data = await callJson("/api/mongodb/databases");
    fillSelect($("database-select"), data.databases.map((item) => item.name), selectedDatabase());
    $("browser-output").textContent = pretty(data);
    await loadCollections();
  }} catch (error) {{
    $("browser-output").textContent = String(error);
  }} finally {{
    setBusy(button, false);
  }}
}}

async function loadCollections() {{
  const button = $("load-collections");
  setBusy(button, true);
  try {{
    const data = await callJson(`/api/mongodb/collections?database=${{encodeURIComponent(selectedDatabase())}}`);
    fillSelect($("collection-select"), data.collections.map((item) => item.name), selectedCollection());
    $("browser-output").textContent = pretty(data);
    updateActiveTarget();
  }} catch (error) {{
    $("browser-output").textContent = String(error);
  }} finally {{
    setBusy(button, false);
  }}
}}

async function inspectCollection() {{
  const button = $("inspect-collection");
  setBusy(button, true);
  try {{
    const data = await callJson(`/api/mongodb/collection/summary?${{targetQuery()}}`);
    $("browser-output").textContent = pretty(data);
    await refreshStatus();
  }} catch (error) {{
    $("browser-output").textContent = String(error);
  }} finally {{
    setBusy(button, false);
  }}
}}

async function createIndex() {{
  const button = $("create-index");
  setBusy(button, true);
  try {{
    const data = await callJson("/api/index/create", {{
      method: "POST",
      body: JSON.stringify(selectedTarget())
    }});
    $("status-output").textContent = pretty(data);
    await refreshStatus();
  }} catch (error) {{
    $("status-output").textContent = String(error);
  }} finally {{
    setBusy(button, false);
  }}
}}

async function extractFromPath() {{
  const button = $("load-path");
  setBusy(button, true);
  try {{
    const data = await callJson("/api/document/extract/path", {{
      method: "POST",
      body: JSON.stringify({{ file_path: $("file-path").value }})
    }});
    applyExtractedDocument(data.document);
  }} catch (error) {{
    $("extract-output").textContent = String(error);
  }} finally {{
    setBusy(button, false);
  }}
}}

async function extractUpload(file) {{
  if (!file) return;
  $("extract-output").textContent = `Reading ${{file.name}}...`;
  try {{
    const buffer = await file.arrayBuffer();
    const data = await callJson("/api/document/extract/upload", {{
      method: "POST",
      body: JSON.stringify({{
        filename: file.name,
        content_base64: arrayBufferToBase64(buffer)
      }})
    }});
    applyExtractedDocument(data.document);
  }} catch (error) {{
    $("extract-output").textContent = String(error);
  }}
}}

function applyExtractedDocument(document) {{
  $("title").value = document.title || document.filename || "Document";
  $("source-id").value = document.source_id || slug($("title").value);
  $("doc-text").value = document.text || "";
  $("chunk-output").textContent = "No chunk preview yet.";
  $("index-output").textContent = "No indexing run yet.";
  $("extract-output").textContent = pretty({{
    filename: document.filename,
    extension: document.extension,
    title: document.title,
    source_id: document.source_id,
    characters: document.characters,
    source_path: document.source_path || "",
    text_preview: (document.text || "").slice(0, 900)
  }});
}}

async function previewChunks() {{
  const button = $("preview-chunks");
  setBusy(button, true);
  try {{
    const data = await callJson("/api/document/chunks", {{
      method: "POST",
      body: JSON.stringify({{
        title: $("title").value,
        source_id: $("source-id").value,
        text: $("doc-text").value,
        ...selectedTarget()
      }})
    }});
    $("chunk-output").textContent = pretty(data);
  }} catch (error) {{
    $("chunk-output").textContent = String(error);
  }} finally {{
    setBusy(button, false);
  }}
}}

async function indexDocument() {{
  const button = $("index-doc");
  setBusy(button, true);
  try {{
    const data = await callJson("/api/index/document", {{
      method: "POST",
      body: JSON.stringify({{
        title: $("title").value,
        source_id: $("source-id").value,
        text: $("doc-text").value,
        ...selectedTarget()
      }})
    }});
    $("index-output").textContent = pretty(data);
    await refreshStatus();
    await refreshMetrics();
  }} catch (error) {{
    $("index-output").textContent = String(error);
  }} finally {{
    setBusy(button, false);
  }}
}}

let chatBusy = false;

function appendChatMessage(role, text, citations = [], insufficientEvidence = false) {{
  $("chat-empty").hidden = true;
  const message = document.createElement("article");
  message.className = `chat-message ${{role}}`;
  const heading = document.createElement("span");
  heading.className = "chat-role";
  heading.textContent = role === "user"
    ? "VISITOR"
    : insufficientEvidence
      ? "LEX // INSUFFICIENT EVIDENCE"
      : "LEX // GROUNDED RESPONSE";
  const answer = document.createElement("p");
  answer.className = "chat-answer";
  answer.textContent = text;
  message.append(heading, answer);

  if (citations.length) {{
    const citationList = document.createElement("div");
    citationList.className = "chat-citations";
    for (const citation of citations) {{
      const item = document.createElement("div");
      item.className = "chat-citation";
      const source = citation.title || citation.source_id || "Portfolio source";
      const section = citation.section ? ` · ${{citation.section}}` : "";
      const scores = [
        Number.isFinite(citation.vector_score) ? `vector ${{citation.vector_score.toFixed(3)}}` : "",
        Number.isFinite(citation.rerank_score) ? `rerank ${{citation.rerank_score.toFixed(3)}}` : ""
      ].filter(Boolean).join(" · ");
      item.textContent = `${{citation.evidence_id || "SOURCE"}} · ${{source}}${{section}}${{scores ? ` · ${{scores}}` : ""}}`;
      citationList.appendChild(item);
    }}
    message.appendChild(citationList);
  }}
  $("chat-transcript").appendChild(message);
  $("chat-transcript").scrollTop = $("chat-transcript").scrollHeight;
}}

function setChatTimings({{ healthMs = null, clientMs = null, timings = {{}}, evidenceCount = null }} = {{}}) {{
  $("chat-health-latency").textContent = Number.isFinite(healthMs) ? `${{healthMs.toFixed(0)}} ms` : "—";
  $("chat-client-latency").textContent = Number.isFinite(clientMs) ? `${{clientMs.toFixed(0)}} ms` : "—";
  $("chat-embedding-latency").textContent = Number.isFinite(timings.embedding) ? `${{timings.embedding}} ms` : "—";
  $("chat-retrieval-latency").textContent = Number.isFinite(timings.retrieval) ? `${{timings.retrieval}} ms` : "—";
  $("chat-rerank-latency").textContent = Number.isFinite(timings.rerank) ? `${{timings.rerank}} ms` : "—";
  $("chat-generation-latency").textContent = Number.isFinite(timings.answer_generation)
    ? `${{timings.answer_generation}} ms`
    : "—";
  $("chat-evidence-count").textContent = Number.isFinite(evidenceCount) ? String(evidenceCount) : "—";
}}

async function checkLexReadiness() {{
  const status = $("chat-health");
  status.dataset.state = "loading";
  status.textContent = "Checking Lex API readiness…";
  const started = performance.now();
  try {{
    const payload = await callJson("/api/status");
    if (typeof payload.mongo_ok !== "boolean" || !payload.mongo_ok) {{
      throw new Error(payload.error || "MongoDB is not connected.");
    }}
    if (payload.config?.chat_model !== "gpt-5.5") {{
      throw new Error(`Lex requires gpt-5.5; API reports ${{payload.config?.chat_model || "unknown"}}.`);
    }}
    status.dataset.state = "success";
    status.textContent = `LEX API READY · ${{(performance.now() - started).toFixed(0)}} ms`;
    return true;
  }} catch (error) {{
    status.dataset.state = "error";
    status.textContent = `LEX API UNAVAILABLE · ${{error.message}}`;
    return false;
  }}
}}

async function askLex(event) {{
  event.preventDefault();
  if (chatBusy) return;
  const question = $("chat-query").value.trim();
  if (question.length < 2) return;

  chatBusy = true;
  const send = $("chat-send");
  send.disabled = true;
  $("chat-query").disabled = true;
  appendChatMessage("user", question);
  const thinking = document.createElement("div");
  thinking.className = "chat-thinking";
  thinking.textContent = "LEX IS SEARCHING THE PROFILE KNOWLEDGE BASE…";
  thinking.setAttribute("role", "status");
  $("chat-transcript").appendChild(thinking);
  $("chat-transcript").scrollTop = $("chat-transcript").scrollHeight;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 180000);
  let started = performance.now();
  let healthMs = null;
  const status = $("chat-health");

  try {{
    const healthStarted = performance.now();
    const ready = await checkLexReadiness();
    healthMs = performance.now() - healthStarted;
    if (!ready) throw new Error(status.textContent);
    status.dataset.state = "loading";
    status.textContent = "ASKING POST /api/ask…";
    started = performance.now();
    const response = await fetch("/api/ask", {{
      method: "POST",
      headers: {{
        "Content-Type": "application/json",
        ...(adminAccessToken ? {{ Authorization: `Bearer ${{adminAccessToken}}` }} : {{}})
      }},
      body: JSON.stringify({{ query: question, top_k: 3, min_score: 0.6 }}),
      cache: "no-store",
      signal: controller.signal
    }});
    let payload;
    try {{
      payload = await response.json();
    }} catch {{
      throw new Error(`Lex API returned a non-JSON response (HTTP ${{response.status}}).`);
    }}
    if (!response.ok) {{
      throw new Error(payload?.error || payload?.detail || `Lex API failed (HTTP ${{response.status}}).`);
    }}
    if (typeof payload.answer !== "string" || !payload.answer.trim()) {{
      throw new Error("Lex API response did not contain an answer.");
    }}
    if (payload.chat_model !== "gpt-5.5") {{
      throw new Error(`Expected gpt-5.5; received ${{payload.chat_model || "unknown model"}}.`);
    }}
    if (!Array.isArray(payload.citations)) {{
      throw new Error("Lex API response did not contain citation metadata.");
    }}
    thinking.remove();
    const clientMs = performance.now() - started;
    const timings = payload.timings_ms || {{}};
    setChatTimings({{
      healthMs,
      clientMs,
      timings,
      evidenceCount: payload.evidence_count
    }});
    appendChatMessage(
      "assistant",
      payload.answer,
      payload.citations,
      payload.insufficient_evidence === true
    );
    status.dataset.state = "success";
    status.textContent = `LEX ANSWER READY · ${{clientMs.toFixed(0)}} ms client · ${{payload.evidence_count || 0}} evidence chunks`;
    await refreshMetrics();
  }} catch (error) {{
    thinking.remove();
    const clientMs = performance.now() - started;
    setChatTimings({{ healthMs, clientMs }});
    status.dataset.state = "error";
    status.textContent = `LEX REQUEST FAILED · ${{clientMs.toFixed(0)}} ms`;
    appendChatMessage(
      "assistant error",
      error.name === "AbortError" ? "The Lex request timed out after 180 seconds." : error.message
    );
    await refreshMetrics();
  }} finally {{
    clearTimeout(timeout);
    chatBusy = false;
    send.disabled = false;
    $("chat-query").disabled = false;
    $("chat-query").focus();
  }}
}}

function resetLexChat() {{
  if (chatBusy) return;
  $("chat-transcript").replaceChildren($("chat-empty"));
  $("chat-empty").hidden = false;
  setChatTimings();
  $("chat-query").value = "";
  $("chat-query").focus();
}}

function escapeHtml(value) {{
  return value.replace(/[&<>"']/g, (char) => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }}[char]));
}}

function arrayBufferToBase64(buffer) {{
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {{
    const chunk = bytes.subarray(offset, offset + chunkSize);
    binary += String.fromCharCode(...chunk);
  }}
  return btoa(binary);
}}

function slug(value) {{
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80) || "document";
}}

function selectedDatabase() {{
  return $("database-select").value || defaultTarget.mongodb_db;
}}

function selectedCollection() {{
  return $("collection-select").value || defaultTarget.mongodb_collection;
}}

function selectedTarget() {{
  return {{
    mongodb_db: selectedDatabase(),
    mongodb_collection: selectedCollection()
  }};
}}

function targetQuery() {{
  const target = selectedTarget();
  return new URLSearchParams({{ database: target.mongodb_db, collection: target.mongodb_collection }}).toString();
}}

function updateActiveTarget() {{
  $("active-target").textContent = `${{selectedDatabase()}}.${{selectedCollection()}}`;
}}

function fillSelect(select, values, preferred) {{
  const unique = [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b));
  if (!unique.includes(preferred)) unique.unshift(preferred);
  select.innerHTML = unique.map((value) => `<option value="${{escapeHtml(value)}}">${{escapeHtml(value)}}</option>`).join("");
  select.value = preferred;
  updateActiveTarget();
}}

$("refresh").addEventListener("click", refreshStatus);
$("refresh-metrics").addEventListener("click", refreshMetrics);
$("metrics-window").addEventListener("change", refreshMetrics);
$("create-index").addEventListener("click", createIndex);
$("load-databases").addEventListener("click", loadDatabases);
$("load-collections").addEventListener("click", loadCollections);
$("inspect-collection").addEventListener("click", inspectCollection);
$("database-select").addEventListener("change", () => {{
  updateActiveTarget();
  loadCollections();
}});
$("collection-select").addEventListener("change", updateActiveTarget);
$("load-path").addEventListener("click", extractFromPath);
$("dropzone").addEventListener("click", () => $("file-input").click());
$("dropzone").addEventListener("keydown", (event) => {{
  if (event.key === "Enter" || event.key === " ") {{
    event.preventDefault();
    $("file-input").click();
  }}
}});
$("file-input").addEventListener("change", (event) => extractUpload(event.target.files[0]));
for (const eventName of ["dragenter", "dragover"]) {{
  $("dropzone").addEventListener(eventName, (event) => {{
    event.preventDefault();
    $("dropzone").classList.add("dragover");
  }});
}}
for (const eventName of ["dragleave", "drop"]) {{
  $("dropzone").addEventListener(eventName, (event) => {{
    event.preventDefault();
    $("dropzone").classList.remove("dragover");
  }});
}}
$("dropzone").addEventListener("drop", (event) => extractUpload(event.dataTransfer.files[0]));
$("preview-chunks").addEventListener("click", previewChunks);
$("index-doc").addEventListener("click", indexDocument);
$("chat-form").addEventListener("submit", askLex);
$("chat-query").addEventListener("keydown", (event) => {{
  if (event.key === "Enter" && !event.shiftKey) {{
    event.preventDefault();
    $("chat-form").requestSubmit();
  }}
}});
$("new-chat").addEventListener("click", resetLexChat);
updateActiveTarget();
refreshStatus();
checkLexReadiness();
</script>
</body>
</html>"""


router = APIRouter()

router.add_api_route("/", home, methods=["GET"], include_in_schema=False)
router.add_api_route(
    "/api/status", status, methods=["GET"], summary="Service status", tags=["system"]
)
router.add_api_route(
    "/api/mongodb/databases",
    mongodb_databases,
    methods=["GET"],
    summary="List MongoDB databases",
    tags=["mongodb"],
)
router.add_api_route(
    "/api/mongodb/collections",
    mongodb_collections,
    methods=["GET"],
    summary="List MongoDB collections",
    tags=["mongodb"],
)
router.add_api_route(
    "/api/mongodb/collection/summary",
    mongodb_collection_summary,
    methods=["GET"],
    summary="Inspect a MongoDB collection",
    tags=["mongodb"],
)
router.add_api_route(
    "/api/index/create",
    instrument_operation(create_index, "indexing"),
    methods=["POST"],
    summary="Create or inspect the vector index",
    tags=["indexing"],
)
router.add_api_route(
    "/api/document/extract/upload",
    extract_uploaded_document,
    methods=["POST"],
    summary="Extract an uploaded document",
    tags=["documents"],
)
router.add_api_route(
    "/api/document/extract/path",
    extract_path_document,
    methods=["POST"],
    summary="Extract a local document path",
    tags=["documents"],
)
router.add_api_route(
    "/api/document/chunks",
    preview_chunks,
    methods=["POST"],
    summary="Preview document chunks",
    tags=["documents"],
)
router.add_api_route(
    "/api/index/document",
    instrument_operation(index_document, "indexing"),
    methods=["POST"],
    summary="Chunk, embed, and store a document",
    tags=["indexing"],
)
router.add_api_route(
    "/api/search",
    instrument_operation(search, "retrieval"),
    methods=["POST"],
    summary="Run MongoDB vector search",
    tags=["retrieval"],
)
router.add_api_route(
    "/api/rerank",
    instrument_operation(rerank, "reranking"),
    methods=["POST"],
    summary="Rerank retrieved candidates",
    tags=["retrieval"],
)
router.add_api_route(
    "/api/ask",
    instrument_operation(ask, "query"),
    methods=["POST"],
    summary="Retrieve evidence and generate a cited answer",
    tags=["answering"],
)
