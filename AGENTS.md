# AGENTS.md

This file gives Codex guidance for working in this repository.

## Project Snapshot

- **Backend**: FastAPI async, Pydantic v2, SQLAlchemy async
- **Frontend**: Vue 3 + Vite + TypeScript
- **Database**: SQLite for local/dev, MySQL for production
- **Infra**: Redis, JWT auth, Alembic migrations
- **Domain**: tutor/order matching, admin backend, teacher H5 board, financial and application workflows

## Working Rules

- Read the existing code before changing behavior.
- Keep edits narrow and aligned with the current module structure.
- Prefer async code for backend routes, service calls, and DB access.
- Validate inputs at boundaries with Pydantic models.
- Reuse existing patterns in routers, services, models, stores, and views.
- Avoid adding new frameworks or abstractions unless the current code clearly needs them.

## Tech Stack Guidance

- **Backend default**: FastAPI + SQLAlchemy async + Pydantic v2
- **Frontend default**: Vue 3; do not introduce Streamlit for this app unless explicitly requested
- **AI / external services**: use the existing integration style for DeepSeek, WeChat, AMap, and Redis-backed rate limiting/caching when relevant
- **Database**: local development may use SQLite; production should support MySQL async URLs

## Code Style

- Write industrial-grade code: handle edge cases, bad inputs, empty states, and missing config.
- Keep functions small and names clear.
- Use minimal comments; only add comments where the intent is not obvious.
- Follow existing naming and file organization.
- Avoid unrelated refactors when making a targeted fix.

## Frontend Guidance

- Match the existing product tone: clean, practical, mobile-friendly, and business-focused.
- Keep UI restrained and readable.
- Do not introduce flashy motion, heavy gradients, or decorative noise.
- Prefer the existing component stack and store/router patterns.
- Preserve role-based flows for teacher, tenant admin, and super admin views.

## Backend Notes

- `main.py` is the FastAPI entry point.
- `database.py` handles engine/session setup and dev seeding.
- `routers/v1/` contains the API surface.
- `services/` holds business logic such as parsing, auth, calculator, recommendation, geo, and scheduler logic.
- `models/` contains domain and schema definitions.

## Common Commands

```bash
# Backend dev
uvicorn main:app --reload --port 8000

# Frontend dev
cd frontend
npm install
npm run dev

# Backend tests
pytest

# Frontend build
cd frontend
npm run build
```

## Notes for This Repo

- Treat `DEV_MODE=true` as local-only behavior that can seed demo data and simplify auth flows.
- Be careful with auth, order status transitions, and financial calculations; they are core business rules.
- If a change touches both backend and frontend, update the API contract and the UI together.

## Agent skills

### Issue tracker

Issues live as local markdown files under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: root `CONTEXT.md` + `docs/adr/`. See `docs/agents/domain.md`.
