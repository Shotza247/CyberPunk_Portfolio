---
noteId: "93370870d90411f1b9ac4ffe5b9fb7f1"
tags: []

---

# Production and Deployment Readiness Workplan

This document is an implementation artifact for a coding agent. Work through it to make the Cyberpunk Portfolio repository production-ready and independently deployable without depending on the separate `MongoDB_RAG` folder/project.

## Goal

Deploy this repository as a complete portfolio application with two production services:

1. **Static frontend** on Render.
2. **FastAPI backend** on Vercel from this same repository.

The separate `MongoDB_RAG` project should remain only a reusable template/reference. The deployed portfolio must not require deploying that separate project first.

## Current architecture

- Static portfolio files live at the repository root:
  - `index.html`
  - `admin.html`
  - `styles.css`
  - `admin.css`
  - `theme-init.js`
  - `portfolio.js`
  - `profile-assistant.js`
  - `badge-admin.js`
- Render static deployment is configured by `render.yaml`.
- Frontend build is handled by `scripts/build_frontend.py`.
- FastAPI backend entrypoint exists at `api/index.py`.
- Backend app is implemented in `src/mongodb_vector_test_ui/api/fastapi.py` and related modules.
- Backend Python package/dependencies are defined by `pyproject.toml` and `requirements.txt`.
- Deployment instructions are in `docs/DEPLOYMENT.md`.

## Non-negotiable production rules

- Do not commit secrets.
- Do not copy values from `.env` into source, docs, examples, logs, commits, or chat.
- Treat `.env.example` as a placeholder-only file.
- Keep public browser code limited to non-secret API origins and display configuration.
- Admin operations must remain authenticated.
- Public profile chat may stay public only if rate/abuse controls are configured.
- The production frontend must not point to `localhost`.
- The backend must be deployable from this repository alone.

## Priority summary

| Priority | Area | Outcome |
|---|---|---|
| P0 | Deployment config | Vercel backend deployment is explicit and reproducible from this repo. |
| P0 | Secrets hygiene | No real secrets are committed; placeholders only. |
| P0 | Public API abuse controls | `/api/ask` and `/api/auth/login` are protected by rate/firewall controls. |
| P1 | MongoDB reliability | Mongo clients have timeouts and a deliberate connection lifecycle. |
| P1 | Frontend/backend config | Render-generated frontend uses the deployed Vercel API origin. |
| P1 | Health/readiness checks | Status checks identify model, database, index, CORS, and config issues. |
| P2 | Documentation | Deployment docs match the actual repository state. |
| P2 | Validation | Tests, build, local API smoke test, and production smoke checklist pass. |

---

## Phase 1 — Repository and deployment configuration

### Task 1.1 — Add root Vercel configuration

**Problem:** The docs state this repo has Vercel deployment config, but the root repo currently does not have `vercel.json`.

**Action:** Add a root `vercel.json` for the FastAPI backend.

Recommended starting point:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "functions": {
    "api/**/*.py": {
      "excludeFiles": "{tests/**,docs/**,templates/**,.github/**,scripts/**,**/__pycache__/**,**/*.pyc}"
    }
  }
}
```

If preview evidence shows the `/api/ask` route needs longer runtime, update the Vercel function settings intentionally and document the reason.

**Acceptance criteria:**

- `vercel.json` exists at the repository root.
- Vercel can import the repo and identify `api/index.py`.
- Docs no longer reference deployment config that is missing from this repo.

### Task 1.2 — Confirm frontend build output

**Action:** Confirm `scripts/build_frontend.py` copies all required static assets into `dist`.

Check whether these are required in production and copied correctly:

- `images/`
- root CSS/JS files
- `index.html`
- `admin.html`
- generated `api-config.js`

**Validation command:**

```powershell
$env:PORTFOLIO_API_BASE_URL="https://example-api.vercel.app"; python scripts\build_frontend.py
```

Then inspect `dist/api-config.js` and confirm it contains the configured API origin, not localhost.

**Acceptance criteria:**

- `dist/api-config.js` is generated.
- The generated API origin is the provided URL.
- No secrets are written into `dist`.

---

## Phase 2 — Secrets and environment hygiene

### Task 2.1 — Remove any real secret material from tracked files

**Action:** Search tracked files for likely secrets before commit.

Use safe checks that do not print secret values where possible.

Suggested commands:

```powershell
git --no-pager status --short
git --no-pager ls-files
```

Manually verify these files only contain placeholders:

- `.env.example`
- `README.md`
- `docs/DEPLOYMENT.md`
- any generated docs

**Important:** `.env` is ignored and should stay untracked. If a real API key was ever committed, rotate it immediately in the provider console.

**Acceptance criteria:**

- `.env` is not tracked.
- `.env.example` contains placeholders only.
- No tracked file contains real API keys, MongoDB credentials, admin password hashes, or signing secrets.

### Task 2.2 — Document required environment variables clearly

Update `docs/DEPLOYMENT.md` if needed so it lists the production variables for Vercel and Render.

**Vercel backend variables:**

- `APP_ENV=production`
- `MONGODB_URI`
- `MONGODB_DB`
- `MONGODB_COLLECTION`
- `VECTOR_INDEX_NAME`
- `VECTOR_FIELD`
- `VECTOR_DIMENSIONS`
- `VECTOR_NUM_CANDIDATES`
- `EMBEDDING_PROVIDER`
- `VOYAGE_BASE_URL`
- `VOYAGE_API_KEY`
- `VOYAGE_MODEL`
- `RERANK_PROVIDER`
- `VOYAGE_RERANK_MODEL`
- `RERANK_TIMEOUT_SECONDS`
- `CHAT_PROVIDER`
- `CHAT_MODEL`
- `CHAT_API_KEY` or provider-specific key such as `OPENAI_API_KEY`
- `CHAT_BASE_URL` if using an OpenAI-compatible gateway
- `CHAT_TEMPERATURE`
- `CHAT_MAX_TOKENS`
- `CHAT_TIMEOUT_SECONDS`
- `CHAT_MAX_RETRIES`
- `ADMIN_USERNAME`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD_HASH`
- `ADMIN_AUTH_SECRET`
- `ADMIN_SESSION_TTL_SECONDS`
- `BADGE_COLLECTION`
- `METRICS_COLLECTION`
- `FRONTEND_ORIGINS`

**Render frontend variable:**

- `PORTFOLIO_API_BASE_URL`

**Acceptance criteria:**

- Docs distinguish Render frontend env vars from Vercel backend env vars.
- Docs explicitly say not to put backend secrets in Render static-site configuration.

---

## Phase 3 — Public endpoint abuse controls

### Task 3.1 — Add rate/abuse controls for production

**Problem:** Public `/api/ask` can trigger paid or expensive operations: embedding, MongoDB vector search, rerank, and chat generation.

**Action options:**

Option A — Preferred for deployment speed:

- Configure Vercel Firewall/rate controls for:
  - `POST /api/ask`
  - `POST /api/auth/login`
  - optionally `GET /api/status`

Option B — Add application-level throttling:

- Implement lightweight IP/origin-aware throttling in FastAPI.
- Keep it serverless-safe. Avoid in-memory-only logic if production instances can scale horizontally.
- If using a persistent rate-limit store, document required env vars.

**Minimum policy recommendation:**

- `/api/ask`: strict per-IP and per-origin limit.
- `/api/auth/login`: stricter brute-force protection.
- Request body size limit for public routes.
- Reject unsupported origins through existing CORS configuration.

**Acceptance criteria:**

- Production plan includes a concrete active rate/abuse control.
- `/api/auth/login` has brute-force protection via platform or app layer.
- `/api/ask` cannot be called unlimited from a public client.
- `docs/DEPLOYMENT.md` documents the chosen control.

---

## Phase 4 — Backend production hardening

### Task 4.1 — Add MongoDB client timeouts and connection lifecycle strategy

**Problem:** `MongoVectorStore` and `PortfolioBadgeStore` create `MongoClient` instances without explicit timeouts or close/reuse behavior.

Relevant files:

- `src/mongodb_vector_test_ui/vectorstore/mongodb.py`
- `src/mongodb_vector_test_ui/vectorstore/badges.py`
- `src/mongodb_vector_test_ui/core/metrics.py`

**Action:** Implement one deliberate strategy:

Strategy A — Cached clients for serverless reuse:

- Create shared Mongo client helpers in a central module.
- Use explicit timeouts.
- Reuse clients across warm invocations.

Strategy B — Per-operation clients with guaranteed close:

- Add explicit timeouts.
- Ensure stores expose `close()` or context manager support.
- Close clients after operations.

Recommended client timeout parameters:

```python
MongoClient(
    settings.mongodb_uri,
    serverSelectionTimeoutMS=3000,
    connectTimeoutMS=3000,
    socketTimeoutMS=10000,
)
```

**Acceptance criteria:**

- Mongo clients have explicit timeouts.
- Code avoids indefinite hangs when Atlas is unreachable.
- Tests cover client options or connection helper behavior without making live network calls.

### Task 4.2 — Improve `/api/status` readiness reporting

**Problem:** The frontend health check verifies MongoDB and the configured chat model name, but not every production readiness issue.

Relevant files:

- `src/mongodb_vector_test_ui/api/operations.py`
- `src/mongodb_vector_test_ui/llm/providers.py`
- `profile-assistant.js`

**Action:** Make `/api/status` more useful for production readiness.

Include safe, non-secret diagnostics such as:

- MongoDB URI present and valid shape.
- MongoDB ping success.
- Document count.
- Vector index list/status.
- Embedding provider/model.
- Rerank provider/model.
- Chat provider/model.
- Chat API key present as boolean only.
- `config_issues` list.
- Admin auth configured as boolean only.
- Frontend origin count.

**Frontend behavior:**

Update `profile-assistant.js` so health fails if critical `config_issues` are present.

**Acceptance criteria:**

- `/api/status` never returns secret values.
- Frontend does not show “ready” when backend config has critical issues.
- Tests cover healthy and unhealthy status responses.

### Task 4.3 — Add a private live smoke path for model acceptance

**Problem:** Health checks can report configured model name without proving the provider accepts live requests.

**Action:** Add an admin-only smoke workflow or documented command to test a real `/api/ask` after indexing profile data.

Do not expose this as a public unauthenticated endpoint unless rate-limited and safe.

**Acceptance criteria:**

- There is a documented preview acceptance step for a real `/api/ask` call.
- The acceptance step proves citation resolution, answer generation, and model access.
- No raw secrets are printed.

---

## Phase 5 — Frontend production readiness

### Task 5.1 — Remove hardcoded model policy from browser or generate it at build time

**Problem:** `profile-assistant.js` hard-requires `gpt-5.5`. This can block a working backend if production uses another approved model.

Relevant file:

- `profile-assistant.js`

Current behavior:

- `RAG_CHAT_MODEL = 'gpt-5.5'`
- Health fails if `/api/status` reports a different model.
- Ask fails if `/api/ask` reports a different model.

**Action options:**

Option A — Build-time config:

- Extend `scripts/build_frontend.py` to generate allowed/expected public model metadata into `api-config.js`.
- Keep browser checks aligned with deployment env.

Option B — Backend-owned policy:

- Remove exact browser-side model enforcement.
- Let backend validate model allowlist and return safe status.
- Browser displays the model for transparency but does not reject solely by exact model string.

**Acceptance criteria:**

- Production model policy is not accidentally hardcoded to an unavailable model.
- The frontend still surfaces backend model details to users/admins.
- Tests are updated for the chosen behavior.

### Task 5.2 — Ensure production frontend never uses localhost

Relevant files:

- `api-config.js`
- `scripts/build_frontend.py`
- `render.yaml`

**Action:** Keep source `api-config.js` as local-development fallback only, but make docs and build enforce production configuration.

**Acceptance criteria:**

- Render build fails if `PORTFOLIO_API_BASE_URL` is missing.
- Render output has the Vercel API origin.
- Production browser requests go to Vercel, not localhost.

---

## Phase 6 — MongoDB Atlas readiness

### Task 6.1 — Confirm required collections

Production uses one configured MongoDB database with separate collections:

- Vector document collection: `MONGODB_COLLECTION`, default `profile_chunks`.
- Badge collection: `BADGE_COLLECTION`, default `portfolio_badges`.
- Metrics collection: `METRICS_COLLECTION`, default `rag_operation_metrics`.

**Acceptance criteria:**

- Collections are distinct.
- `METRICS_COLLECTION` is not the vector or badge collection.
- `BADGE_COLLECTION` is not the vector collection.

### Task 6.2 — Confirm vector index exists and matches settings

The desired index is defined in `MongoVectorStore.desired_vector_index_definition()`.

Expected fields:

- Vector field path from `VECTOR_FIELD`, default `embedding`.
- Dimensions from `VECTOR_DIMENSIONS`, default `1024`.
- Similarity: `cosine`.
- Filter fields:
  - `metadata.source_id`
  - `metadata.title`
  - `metadata.section`
  - `chunk_id`

**Acceptance criteria:**

- Atlas Vector Search index exists.
- Index name matches `VECTOR_INDEX_NAME`.
- Dimensions match embedding provider output.
- `/api/status` reports index information.
- `/api/ask` returns candidates for known profile questions.

### Task 6.3 — Seed or index production profile content

**Action:** Ensure production MongoDB has the indexed profile documents needed by Lex.

Use the authenticated workbench or existing indexing route:

- `POST /api/index/document`

**Acceptance criteria:**

- `/api/status` reports a non-zero `document_count`.
- Known profile questions return grounded answers and citations.
- Insufficient-evidence behavior works for unrelated questions.

---

## Phase 7 — Tests and validation

### Task 7.1 — Run local tests

Use the project’s existing test suite.

Recommended commands:

```powershell
python -m pip install -e ".[dev,orchestration,openai]"
python -m pytest
```

If package installation fails because the virtual environment is broken, recreate the project virtual environment instead of installing globally.

**Acceptance criteria:**

- Tests pass locally.
- Any changed behavior has updated tests.

### Task 7.2 — Run local frontend build

```powershell
$env:PORTFOLIO_API_BASE_URL="http://localhost:8765"; python scripts\build_frontend.py
```

**Acceptance criteria:**

- Build completes.
- `dist` contains expected static files.
- `dist/api-config.js` points to the configured URL.

### Task 7.3 — Run local API smoke test

Start the API:

```powershell
python -m uvicorn mongodb_vector_test_ui.api.fastapi:app --host 127.0.0.1 --port 8765
```

In another terminal:

```powershell
curl http://127.0.0.1:8765/api/status
```

If local env is fully configured and indexed, also test:

```powershell
curl -X POST http://127.0.0.1:8765/api/ask -H "Content-Type: application/json" -d "{\"query\":\"What does Jabulani do?\",\"top_k\":3,\"min_score\":0.6}"
```

**Acceptance criteria:**

- `/api/status` returns JSON.
- `/api/ask` returns either a grounded answer with citations or a controlled insufficient-evidence response.
- No stack traces or secret values are returned.

---

## Phase 8 — Production deployment checklist

### Vercel backend

1. Create/import Vercel project from this repository.
2. Confirm root directory is repository root.
3. Confirm `api/index.py` is the backend entrypoint.
4. Configure all backend env vars in Vercel only.
5. Deploy preview.
6. Test preview `/api/status`.
7. Test preview admin login.
8. Test preview badge reads/writes.
9. Test preview `/api/ask` with indexed data.
10. Enable/configure Vercel Firewall or rate controls.
11. Promote to production only after smoke tests pass.

### Render frontend

1. Create Render static site from this repository.
2. Use `render.yaml` or configure manually.
3. Set build command:

```powershell
python scripts\build_frontend.py
```

4. Set publish directory:

```text
dist
```

5. Set `PORTFOLIO_API_BASE_URL` to the Vercel API production origin.
6. Deploy.
7. Add Render production origin to Vercel `FRONTEND_ORIGINS`.
8. Redeploy Vercel backend.
9. Test frontend chat, public badges, admin login, and workbench iframe.

---

## Final production acceptance checklist

The project is production-ready only when all items are complete:

- [ ] Root `vercel.json` exists and is committed.
- [ ] Render build succeeds and generates `dist/api-config.js` with the Vercel API origin.
- [ ] `.env` is untracked.
- [ ] No tracked file contains real secrets.
- [ ] Vercel backend env vars are configured.
- [ ] Render frontend env var `PORTFOLIO_API_BASE_URL` is configured.
- [ ] Vercel `FRONTEND_ORIGINS` includes the exact Render origin.
- [ ] `/api/status` works in production.
- [ ] `/api/status` reports MongoDB connected.
- [ ] `/api/status` reports expected model/provider diagnostics without secrets.
- [ ] Atlas vector index exists and matches configured dimensions.
- [ ] Production profile content is indexed.
- [ ] `/api/ask` returns grounded answers for expected portfolio questions.
- [ ] `/api/ask` handles unrelated questions safely.
- [ ] `/api/auth/login` is protected against brute force.
- [ ] `/api/ask` has public abuse/rate protection.
- [ ] Admin sign-in works.
- [ ] Admin sign-out works.
- [ ] Admin token expires as configured.
- [ ] Public badges load on the portfolio.
- [ ] Admin can create and delete a badge.
- [ ] Metrics collection records operations without raw query/document text.
- [ ] Tests pass locally.
- [ ] Deployment docs match the actual deployed architecture.

## Suggested implementation order for a coding agent

1. Add root `vercel.json`.
2. Fix docs to remove ambiguity around `MongoDB_RAG` dependency.
3. Harden MongoDB client creation.
4. Improve `/api/status` readiness and frontend health behavior.
5. Decide and implement model policy handling in the browser/backend.
6. Add or document rate limiting/firewall controls.
7. Add/update tests for changed behavior.
8. Run `python -m pytest`.
9. Run frontend build test.
10. Perform local API smoke test.
11. Update `docs/DEPLOYMENT.md` with final production steps.

## Notes for future maintainers

- This repo should be treated as the deployable application.
- `MongoDB_RAG` can remain a source template, but production should not require a second project unless intentionally split again.
- If the backend is split into a separate repo later, update Render `PORTFOLIO_API_BASE_URL`, Vercel docs, and README so there is only one source of truth.
