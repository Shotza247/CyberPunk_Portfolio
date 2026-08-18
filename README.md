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
