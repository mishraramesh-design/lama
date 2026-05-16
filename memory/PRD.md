# MigrationOS — Product Requirements Document

## Original Problem Statement
Full-stack legacy application migration assistant. FastAPI backend + React frontend + MongoDB (all app data). Stage 1 (Discovery + SRS) is the pilot scope. Stages 2-5 are sidebar placeholders for now. Architecture: 3 layers — Project Manager (multi-project), KB Engine (per-project, OWL → TOON), Prompt Library (global + project overrides).

## User Choices (locked)
- LLM: **OpenRouter** (key supplied) — deepseek-chat, deepseek-coder, qwen2.5-72b.
- DB: **MongoDB only** for MigrationOS. PostgreSQL is the *target* of migrated apps, not used by MigrationOS itself.
- Stages 2-5: **Scaffold as locked "Coming Soon"** cards in sidebar.
- GitHub push: **stub** (returns success message).
- Pilot seed: **auto-create** "PMIS Migration Pilot" on first run (PHP 8 / CodeIgniter 4 / MariaDB → FastAPI / Python 3.12 / PostgreSQL).

## User Personas
1. **Migration Architect** — admin who configures global prompts and reviews SRS.
2. **Domain SME / Project Owner** — uploads legacy files, answers gap questions, edits/freezes SRS.

## Core Requirements
- Multi-project switcher with per-project KB and SRS.
- KB pipeline: upload (.php/.sql/.pdf/.docx/.csv/.txt) → chunk → OWL extract (classes/methods/tables/cols/FKs/routes) → TOON serialise → cache.
- RAG chat: per-message model selector, token counter, type-ahead suggestions from glossary, gap-question prompt grounded in TOON.
- IEEE 830 SRS: 8 sections, inline-edit, freeze/unfreeze with timestamps, PDF export.
- Prompt Library: 8 seeded global prompts; per-project overrides; versioned.
- Audit log.
- Context-sensitive ? tooltips on every key control.

## Architecture
- Backend: `/app/backend/server.py` (FastAPI) → routers in `/app/backend/routes/{projects,kb,chat,srs,prompts,github,audit}.py`. Utilities: `llm.py` (OpenRouter httpx client), `kb/{parsers,owl_extractor,toon}.py`, `seed.py`, `db.py`, `models.py`.
- Frontend: `/app/frontend/src/App.js` with `BrowserRouter`. Sidebar + 3-panel `Discovery` page (Upload | Chat | SRS). Routes: `/`, `/prompts`, `/audit`. State: `ProjectContext`.
- DB: MongoDB collections `projects, kb_files, kb_chunks, kb_entities, kb_toon, conversations, messages, srs_documents, prompts, project_prompts, audit_log`.

## What's Been Implemented (2026-02)
- ✅ Backend: all 20+ endpoints under `/api/` (projects, kb, chat, srs, prompts, github stub, audit) — 21/21 tests passing.
- ✅ OpenRouter integration with 3 models (deepseek-chat/coder, qwen2.5-72b).
- ✅ TOON serialiser + OWL extraction for PHP and SQL.
- ✅ Frontend: Sidebar with 5-stage lock pipeline, project switcher + new-project dialog.
- ✅ Discovery page: 3-panel (Upload + KB Health + Chat + SRS).
- ✅ SRS generate / inline-edit / freeze / unfreeze / PDF export.
- ✅ Prompt Library page (global + project tabs, versioned cards).
- ✅ Audit log page.
- ✅ Auto-seed of PMIS Migration Pilot + 8 global prompts.
- ✅ Context-sensitive ? tooltips throughout.
- ✅ Type-ahead chat suggestions from KB glossary.

## Backlog
**P0** — none.
**P1** — Replace `dict` payloads with Pydantic models in `/api/kb/build`, `/api/srs/generate`, `/api/srs/freeze`, `/api/srs/unfreeze` for stricter validation.
**P2** — Migrate from deprecated `@app.on_event` to FastAPI `lifespan` context.
**P2** — Return 404 (or explicit `exists` flag) from `GET /api/srs/{id}` when no SRS exists.
**P2** — Streaming chat responses (currently single-shot).

## Next Phases (deferred Stages 2-5)
- **Stage 2 — DataModel**: schema normalisation suggestions for target stack.
- **Stage 3 — Architecture**: microservice decomposition.
- **Stage 4 — CodeGen**: target code generation + unit tests + real GitHub push.
- **Stage 5 — Living**: Selenium tests, SRS diffs, monitoring.
