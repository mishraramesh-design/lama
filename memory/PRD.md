# LAMA — Legacy Application Modernization & Alignment — PRD

(Renamed from "MigrationOS" in iteration 2.)

## Original Problem Statement
Full-stack legacy application migration assistant. FastAPI backend + React frontend + MongoDB. Stage 1 (Discovery + SRS) is the pilot scope. Stages 2-5 are sidebar placeholders. Three layers: Project Manager, KB Engine (OWL → TOON), Prompt Library (global + project overrides).

## User Choices
- LLM: **OpenRouter** (key supplied) — deepseek-chat, deepseek-coder, qwen2.5-72b.
- DB: **MongoDB only**. PostgreSQL is the *target* of migrated apps.
- Single-tenant, single-project at a time (no project switcher in UI; project APIs remain for internal use).
- Stages 2-5: sidebar "Coming Soon" cards.
- GitHub: real push of `docs/SRS.md` after SRS freeze (PyGithub). Stages 2-4 push paths still stubs.
- Pilot seed: auto-create "PMIS Migration Pilot" (PHP 8 / CodeIgniter 4 / MariaDB → FastAPI / Python 3.12 / PostgreSQL).

## User Personas
1. **Migration Architect** — admin who configures global prompts and reviews SRS.
2. **Domain SME / Project Owner** — points LAMA at a folder of legacy code, answers gap questions, edits/freezes SRS, configures GitHub push.

## Core Requirements
- KB ingest: **folder-path scan** (primary) + individual file upload (secondary). Skips `node_modules`, `.git`, `vendor`, `__pycache__`, and backup patterns (`*.bak`, `*.save`, `*_bkp`, `*_old`, `*_backup`, `*.php_*`).
- ZIP archives auto-extracted in memory.
- OWL extraction (PHP/SQL) + TOON serialisation cached per project.
- RAG chat with stage-aware **TOON pruning** (Discovery prioritises CLASSES/ROUTES, DataModel prioritises TABLES, etc.).
- Chat **intent detection**: if user says "generate SRS" (or similar), the SRS is auto-generated and the UI panel auto-refreshes (`srs_triggered: true` in chat response).
- IEEE 830 SRS: 8 sections, inline-edit, freeze/unfreeze, PDF + markdown export.
- GitHub Settings: save repo URL + PAT + branch, Test Connection (calls api.github.com/repos), Push SRS (commits `docs/SRS.md` via PyGithub).
- Prompt library (8 seeded), versioned, per-project overrides.
- Audit log of all key actions.
- Context-sensitive `?` tooltips on every key control.

## Architecture
- Backend (`/app/backend`): `server.py` registers `/api` routers (`projects, kb, chat, srs, prompts, github, audit`). Utilities: `llm.py` (OpenRouter httpx), `kb/{parsers,owl_extractor,toon}.py`, `seed.py`, `db.py`, `models.py`.
- Frontend (`/app/frontend/src`): `App.js` registers routes `/`, `/prompts`, `/settings`, `/audit`. Single-tenant sidebar (LAMA brand + active project header + 5-stage pipeline + bottom nav). Discovery page = 3-panel grid (Upload | Chat | SRS).
- DB: MongoDB collections — `projects, kb_files, kb_chunks, kb_entities, kb_toon, conversations, messages, srs_documents, prompts, project_prompts, audit_log`.

## What's Been Implemented
**Iteration 1 (initial MVP):**
- Backend: all 20+ `/api` endpoints (21/21 tests passing).
- OpenRouter integration with 3 models.
- TOON serialiser + OWL extraction for PHP and SQL.
- Frontend: Sidebar with 5-stage lock pipeline, project switcher + dialog (later removed).
- Discovery page: 3-panel (Upload + KB Health + Chat + SRS).
- SRS generate / inline-edit / freeze / unfreeze / PDF export.
- Prompt Library + Audit Log pages.
- Auto-seed of PMIS Migration Pilot + 8 global prompts.

**Iteration 2 (LAMA rename + folder/GitHub/intent):**
- Renamed everywhere: brand, FastAPI title, logger, page title.
- Removed multi-project switcher from sidebar; project APIs retained internally.
- Sidebar header now shows static active-project info (name + source → target tech).
- New ingest mode: `POST /api/kb/scan-folder` with skip-patterns (fixed ordering bug surfaced by tests).
- ZIP archive support in `parse_file()`.
- `routes/chat.py`: `detect_intent()` + `prune_toon()` + auto-SRS-trigger (`srs_triggered` flag).
- `routes/github.py`: real `POST /api/github/config`, `GET /api/github/config/{id}`, `POST /api/github/test`, `POST /api/github/push` (uses PyGithub to commit `docs/SRS.md`).
- New page `/settings` (GitHubSettingsPage) with config form, Test Connection, folder-tree preview, Push SRS button.
- PyGithub + requests added to `requirements.txt`.

## Backlog
**P1** — Replace `dict` payloads with Pydantic models on `/api/kb/scan-folder`, `/api/kb/build`, `/api/srs/generate|freeze|unfreeze`.
**P1** — Surface SRS auto-trigger failures in chat response (currently silently `false`).
**P2** — Migrate from deprecated `@app.on_event` to FastAPI `lifespan`.
**P2** — `GET /api/srs/{id}` return 404 (or `exists` flag) when no SRS.
**P2** — `token_preview` should show last 4 chars (not first 6).
**P2** — Streaming chat responses.
**P2** — Batched insert for very large folder scans.

## Next Phases
- **Stage 2 — DataModel**: target schema normalisation; push `schema/*.sql` to GitHub.
- **Stage 3 — Architecture**: microservice decomposition.
- **Stage 4 — CodeGen**: full target backend/frontend + Dockerfile; full GitHub push.
- **Stage 5 — Living**: Selenium tests, SRS diffs, monitoring.
