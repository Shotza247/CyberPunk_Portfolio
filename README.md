# Jabulani Ndlovu Portfolio

Static cyberpunk-style portfolio for Jabulani Ndlovu, positioned around Data & AI Engineering, analytics systems, agentic AI, APIs, and enterprise solution delivery.

## Current Scope

- Single-page portfolio in `index.html`
- Profile narrative based on `Jabulani Ndlovu - Master Career Profile.txt`
- Floating Profile Assistant powered by local key-value matching
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

Open `index.html` directly in a browser. No build step is required for the current static site.

## Next Architecture Direction

The floating Profile Assistant is currently a local keyword matcher. The planned evolution is:

1. MVP 1: keep the static site, improve the local assistant knowledge structure.
2. MVP 2: add a hosted RAG API using MongoDB Atlas Vector Search and Voyage AI embeddings.
3. MVP 3: add an OpenAI embeddings path and agentic tool-calling capabilities.

See `ROADMAP_ISSUES.md` for proposed milestones, issue backlog, and vector database options.

## Feature Log

### 2026-08-21 - Theme Toggle & Visual Polish

- Added a persistent light/dark theme toggle in the top navigation.
- Added a dedicated light palette instead of a simple color inversion, avoiding white text on white backgrounds.
- Updated the four core pillar cards with mode-aware accent colors: Data, Systems, AI, and Delivery now use coordinated cyan, gold, violet, and magenta accents.
- Updated the Profile Assistant visual treatment so chat panels, message bubbles, suggestion chips, inputs, tooltips, and analytics remain readable and aligned in both dark and light modes.
- Theme preference is stored locally in the visitor's browser.

## Documentation Convention

Every new feature, visual improvement, assistant capability, architecture change, or meaningful content correction should be recorded in the Feature Log with the date, what changed, and why it matters.
