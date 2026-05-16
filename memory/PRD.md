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

**Iteration 3-4 (EY theme, Qdrant RAG, SSE, StageContext):**
- EY rebrand (yellow/navy).
- Qdrant vector store + semantic RAG for SRS sections.
- SSE per-section streaming SRS generation with keepalive pings.
- Resizable + collapsible 3-panel layout (`react-resizable-panels@2.1.7`).
- Markdown rendering + inline edit in SRS panel.
- `StageContext` persistence model + `pipeline.py` loader.
- `GET /api/projects/{id}/pipeline` for sidebar badges.

**Iteration 5 (this iteration — Sidebar fix + Section 9 ER + OWL export):**
- 🔧 Fixed corrupted `routes/projects.py` syntax error (line 37 was `e")` instead of `@router.get("/{project_id}/pipeline")`) — backend was failing to boot.
- 🔧 Added missing `useEffect` + `getPipelineStatus` imports to `Sidebar.jsx`.
- 🔧 Wired expanded sidebar `STAGES.map` to use new `stageStatus()` helper with **Frozen v{N} / Ready / Soon** badges (data-testid: `stage-{key}-badge-frozen|ready|locked`).
- ✨ **Section 9 — Entity Relationship Model** added to SRS pipeline:
  - `_gen_entity_model()` computes ER data deterministically from `kb_entities` (no LLM): nodes (with x/y/domain/columns/pk), edges (FK relationships), domain clusters, stats.
  - `SECTION_CONFIGS` now has 9 entries; `_gen_one_section()` branches for `entity_model`.
  - Frontend `ERDiagram.jsx` (D3 force-directed graph): zoom/pan, drag nodes, search, show/hide logs tables, click to see column detail.
  - PDF export renders Section 9 as text-only summary ("N tables across D domains with R FK relationships").
- ✨ **OWL/JSON-LD context download** — `GET /api/kb/{id}/owl-export`:
  - Returns full ontology: `@graph` (classes/tables/routes/roles), `data_model_hints` (high_risk, audit/lookup/junction classification, domains), `microservice_hints` (suggested service boundaries), `migration_context` (stats + SRS purpose summary).
  - "Download OWL Context" button in KB Health card (`data-testid=owl-export-btn`).
- 📦 New dependency: `d3@7.9.0` (frontend).
- ✅ Testing agent: 11/11 checkpoints PASS (6/6 backend, 5/5 frontend). Verified on project `7a0b9827-…` with 525 tables / 208 FKs / 42 domains.

**Iteration 6 (Prompt 3/4 verification + Qdrant prod config):**
- 🔧 `GithubTestRequest.repo_url` is now optional (default `""`) — token-only POST returns 200 instead of 422.
- 🟢 All 5 changes in user Prompt 3 (EY colours, resizable panels, SRS markdown, Chat SRS Edit Mode, Qdrant production config) were already implemented in iterations 3-5 — verified by audit grep + smoke tests.
- 🔑 Set `QDRANT_API_KEY` env var in `backend/.env`. Qdrant client now authenticates against `http://93.127.194.188:6333`; collection auto-creates on next Build KB.
- ✅ End-to-end smoke-test of Chat SRS Edit Mode: real LLM call returned 10 well-formed FR requirements grounded in actual KB entities (`AdminController.exportClaims`, `pmis_claims` table) — 4121 tokens, sub-60s.

## Backlog
**P0** — None (Prompt 2/4 complete).
**P1 (User-driven, upcoming Prompts 3-4 in series)** — Wait for next prompt from user.
**P1** — Implement functional backends for pipeline stages 2-5 (DataModel, Architecture, CodeGen, Living). Currently UI placeholders.
**P1** — Un-stub GitHub code push for CodeGen stage.
**P1** — Replace `dict` payloads with Pydantic models on `/api/kb/scan-folder`, `/api/kb/build`, `/api/srs/generate|freeze|unfreeze`.
**P2** — Fix nested-button HTML in `Sidebar.jsx` (HelpIcon Radix Tooltip trigger inside `<button>` causes React hydration warning).
**P2** — Surface SRS auto-trigger failures in chat response (currently silently `false`).
**P2** — Migrate from deprecated `@app.on_event` to FastAPI `lifespan`.
**P2** — `GET /api/srs/{id}` return 404 (or `exists` flag) when no SRS.
**P2** — Streaming chat responses.

## Next Phases
- **Stage 2 — DataModel**: target schema normalisation; push `schema/*.sql` to GitHub.
- **Stage 3 — Architecture**: microservice decomposition.
- **Stage 4 — CodeGen**: full target backend/frontend + Dockerfile; full GitHub push.
- **Stage 5 — Living**: Selenium tests, SRS diffs, monitoring.
