---
noteId: "8f6160e0d5fa11f1a7e9ef15f2fb5506"
tags: []

---

# Cyberpunk Portfolio: Render + Vercel

The portfolio and MongoDB/RAG service now live in this repository. Deploy one
repository twice: Render serves the static portfolio, while Vercel runs the Python
API. `MongoDB_RAG` remains the reusable backend template; its changes are not needed
for this combined application.

## Deployment layout

- **Render static site:** `index.html`, `admin.html`, and the badge client.
- **Vercel Python function:** `api/index.py` exports the FastAPI application.
- **MongoDB Atlas:** stores RAG documents and the separate `portfolio_badges`
  collection.
- **Admin authentication:** one owner account, verified only by the API.

Badge writes and all MongoDB workbench operations require a signed bearer token.
Public portfolio reads, backend status, and profile `/api/ask` remain available
without an admin token. `/api/ask` is pinned to the configured MongoDB database and
collection; clients cannot select another database or collection.

## Vercel backend

Create a Vercel project from this repository with the repository root as its root
directory. Set the following values in Vercel Project Settings > Environment
Variables; never commit them:

- The existing backend settings from `.env.example`, including `MONGODB_URI`,
  embedding credentials, and chat-provider credentials.
- `ADMIN_USERNAME`: the owner account's username.
- `ADMIN_EMAIL`: the same account's email address.
- `ADMIN_PASSWORD_HASH`: generated as described below.
- `ADMIN_AUTH_SECRET`: a private random value with at least 32 characters.
- `FRONTEND_ORIGINS`: the exact Render site origin, for example
  `https://your-portfolio.onrender.com`. Local development may include
  `http://127.0.0.1:5500` and `http://localhost:5500`.
- `ADMIN_SESSION_TTL_SECONDS`: optional; defaults to 3600, with a supported range
  of 300 to 86400.
- `BADGE_COLLECTION`: optional; defaults to `portfolio_badges`.
- `METRICS_COLLECTION`: optional; defaults to `rag_operation_metrics` in the
  configured `MONGODB_DB`. Keep it separate from the vector and badge collections.

The owner-only operations dashboard records query, retrieval, reranking, and
indexing duration, stage latency, success/failure status, result counts, and
approximate token counts in `METRICS_COLLECTION`. Token counts use a rough
four-characters-per-token estimate, not provider billing usage. Telemetry does not
store raw query, answer, or indexed document text. `/api/metrics` requires an admin
session and returns recent aggregate summaries (up to 500 records per selected
window).

Generate and set a password hash locally from an installed project environment:

```powershell
python scripts\create_admin_password_hash.py
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

The first command prompts twice without echoing the password and prints only its
PBKDF2-SHA256 hash. Put that hash in Vercel as `ADMIN_PASSWORD_HASH`; never use the
plaintext password as a Vercel variable. The second command prints a random signing
secret. Do not paste either value into source files, commits, chat, or Render's
public frontend configuration.

The admin account has no public registration or password-reset route. Change the
owner credentials through Vercel environment variables and redeploy. The browser
keeps the short-lived bearer token in memory only; refresh the admin page to sign in
again. Sign out clears the dashboard and its authenticated workbench frame.

## Render frontend

Create a Render Static Site from the same GitHub repository and use the included
`render.yaml` Blueprint, or configure these values manually:

- Build command: `python scripts/build_frontend.py`
- Publish directory: `dist`
- Build environment variable `PORTFOLIO_API_BASE_URL`: the public Vercel deployment
  origin, for example `https://your-api.vercel.app`

The build writes that public URL into `dist/api-config.js`. It contains no credentials.
Set the exact deployed Render origin in Vercel's `FRONTEND_ORIGINS`, then redeploy
the API. CORS intentionally rejects wildcard origins and non-local HTTP origins.

## Local verification

Install the project and run the existing tests:

```powershell
python -m pip install -e ".[dev,orchestration,openai]"
python -m pytest
python -m uvicorn mongodb_vector_test_ui.api.fastapi:app --host 127.0.0.1 --port 8765
```

Serve the portfolio from the same local origin configured in `FRONTEND_ORIGINS`,
for example port 5500. Build the Render output locally by setting
`PORTFOLIO_API_BASE_URL=http://localhost:8765` before running the build command.

The admin page embeds the Lex operations dashboard and sends its token only through
`postMessage` to the exact API origin. The Vercel API accepts that transfer only when
the sender origin is in `FRONTEND_ORIGINS`. Never put a bearer token in a URL.

Before making the profile assistant public, add Vercel Firewall/rate controls to
`/api/auth/login` and the public `/api/ask` route, and verify CORS, Atlas network
access, account setup, signed-in operations, sign-out, token expiry, public badge
rendering, and the deployed model call.
