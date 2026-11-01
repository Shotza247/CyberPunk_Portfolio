# Jabulani Ndlovu Portfolio

Static cyberpunk-style portfolio for Jabulani Ndlovu, positioned around Data & AI Engineering, analytics systems, agentic AI, APIs, and enterprise solution delivery.

## Current Scope

- Single-page portfolio in `index.html`
- Portfolio and admin styles live in `styles.css` and `admin.css`; page behavior is
  separated into `theme-init.js`, `portfolio.js`, `profile-assistant.js`, and
  `badge-admin.js`.
- Profile narrative based on `Jabulani Ndlovu - Master Career Profile.txt`
- Floating Profile Assistant (Lex) checks the MongoDB/RAG `/api/status`, then calls `/api/ask` for grounded answers. The API origin is generated into the Render frontend build.
- Sections for profile, experience, technical capabilities, education, systems/projects, leadership, learning, technology stack, and contact

## Positioning

Core message:

> Data-driven first. AI-enabled second.

The portfolio should show that Jabulani can connect:

- Trusted data foundations
- Analytics and operational intelligence
- APIs and backend services
- LLM applications and agentic workflows
- Enterprise requirements, governance, and stakeholder communication

## Important Claim Rules

Use careful evidence language:

- `Built`: personally implemented
- `Contributed`: actively implemented a portion
- `Supported`: assisted a workstream or team
- `Exposed`: worked around the technology or business context
- `Trained`: completed learning/labs
- `Certified`: only when a formal credential is verified
- `In Progress`: currently learning or building

Do not promote training into certification, exposure into ownership, or concepts into production systems.

## Local Use

Serve the portfolio over HTTP; the admin console is at `/admin.html`. Backend and
deployment setup is documented in [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md).

## Combined Backend + Admin

- The MongoDB/RAG FastAPI application, tests, scripts, templates, and docs are now
  included in this repository. `Shotza247/MongoDB_RAG` remains the reusable template.
- Render serves the static portfolio; Vercel runs the Python API from `api/index.py`.
- Admin access requires the configured username, email, and password. Password
  verification and signed session tokens stay server-side; there is no public signup.
- The admin console manages shared MongoDB-backed portfolio badges and embeds the
  authenticated Lex operations dashboard for query, retrieval, reranking, and indexing.
- Operation latency, stage timing, estimated token counts, success status, and result
  counts are recorded in the configured MongoDB metrics collection. Raw query and
  document text are not stored in telemetry.
- Browser code contains only the public API origin. Provider and database credentials
  belong in Vercel environment variables.

## Profile Assistant Integration

Lex checks `GET /api/status` before sending questions to `POST /api/ask` at the
shared API origin (`http://localhost:8765` locally). It requests the top 3
chunks and requires the backend to report `gpt-5.5`; another model is shown as an
error instead of being used. Answers are prompted to be direct and brief. Evidence
citations and vector/rerank scores are available in a collapsed dropdown. The local
keyword fallback is temporarily disabled so API errors remain visible while debugging.
Topic matching is only used to preserve the relevant portfolio-section link.
No model or database credentials are included in browser code. Public API rollout
still requires the deployment acceptance and rate-control steps in
`docs/DEPLOYMENT.md`.

For local browser testing, serve the portfolio over HTTP on port 5500 and run the
combined API on port 8765. Confirm `/api/status` reports `gpt-5.5` and MongoDB is
connected. Opening the HTML as `file://` uses an opaque origin and is not supported.

The public Vercel endpoint must stay disabled until grounded answers, citation
resolution, CORS, target restrictions and rate controls have passed preview checks.
The other MongoDB APIs are available from the authenticated workbench embedded in
the admin console at `admin.html`.

See `ROADMAP_ISSUES.md` for proposed milestones, issue backlog, and vector database options.

The original MongoDB RAG project is retained as a reusable template. This repository
contains its Vercel entry point and deployment config; their presence does not mean
the combined API has been deployed.

Current handoff: Lex checks the backend's `/api/status` response before `/api/ask`,
displays request and backend stage timings, and shows API errors without substituting
a local answer. Keep the deployed
Vercel endpoint disabled until preview acceptance and API security controls are complete.

## Feature Log

### 2026-11-01 - Local RAG Answers In Lex

- Connected Lex to the local FastAPI `/api/ask` endpoint for synthesized answers.
- Made generated answers concise and moved evidence citations and scores into a
  collapsed dropdown, preserving relevant section links.
- Added a status-first request flow, surfaced API errors instead of falling back,
  and exposed backend embedding, retrieval, rerank, and answer-generation timings.
- Kept the deployed Vercel endpoint commented out pending preview acceptance.

### 2026-11-01 - Cyberpunk Admin + Badge Links

- Added a cyberpunk-styled admin console for adding and removing HTTPS badge links.
- Custom badge links render in the portfolio's credentials section and are stored in
  the MongoDB `portfolio_badges` collection.
- Renamed the portfolio agent from Nexus to Lex and configured its local API target.

### 2026-11-01 - Combined MongoDB Backend + Admin Sign-In

- Migrated the MongoDB/RAG backend, Vercel entrypoint, tests, deployment files, scripts,
  templates, and docs into this repository.
- Added owner-only username/email/password sign-in, server-side PBKDF2 password
  verification, signed expiring bearer sessions, and protected MongoDB admin routes.
- Added shared MongoDB-backed badge CRUD and made public badge cards load from the API.
- Added Render static-site configuration and generated frontend API-origin config.
- Restricted browser CORS to exact configured origins and pinned public profile asks
  to the configured MongoDB database and collection.

### 2026-10-25 - Profile Chat RAG Integration Plan

- Documented the existing /api/ask backend as the planned source for website chat.
- Kept the local keyword assistant as a fallback until hosted API and browser acceptance pass.
- Recorded citation, insufficient-evidence, error, CORS, and deployment acceptance gates.
- This is documentation and planning; no website or backend integration shipped.

### 2026-10-25 - RAG Answer Verification Handoff

- Recorded that the backend requests typed `GroundedAnswer` structured output after
  the pre-fix `gpt-5.1` call failed JSON parsing.
- Focused tests and a post-fix live request remain pending; no successful answer or
  citation acceptance is claimed.
- Kept the website's local matcher active until backend and preview acceptance pass.

### 2026-08-21 - Theme Toggle & Visual Polish

- Added a persistent light/dark theme toggle in the top navigation.
- Added a dedicated light palette instead of a simple color inversion, avoiding white text on white backgrounds.
- Updated the four core pillar cards with mode-aware accent colors: Data, Systems, AI, and Delivery now use coordinated cyan, gold, violet, and magenta accents.
- Updated the Profile Assistant visual treatment so chat panels, message bubbles, suggestion chips, inputs, tooltips, and analytics remain readable and aligned in both dark and light modes.
- Theme preference is stored locally in the visitor's browser.

## Documentation Convention

Every new feature, visual improvement, assistant capability, architecture change, or meaningful content correction should be recorded in the Feature Log with the date, what changed, and why it matters.
