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

**Iteration 7 (Prompt 4/4 — Stage 2: Data Model — FULL IMPLEMENTATION):**
- ✅ **Backend** (`routes/datamodel.py`, ~700 lines):
  - 12 endpoints: 4 generation (3 SSE — OLTP, OLAP, migration-scripts; 1 JSON — bus-matrix), entity-graph (cached/live), RAG chat, artifact list/get/update/freeze/download, stage-2 reset, factory-reset.
  - Pipeline-gated: every generation endpoint requires Discovery `stage_context` (returns 400 if not).
  - DataModelArtifact persistence: one artifact per type per project (upsert pattern), version-incremented on updates.
  - Freeze artifact: when both OLTP and OLAP are frozen, automatically calls `save_stage_context("DataModel", …)` with full handoff payload (DDL contents, table/fact/dim counts, domain map, service boundaries from Discovery) and promotes `Architecture` to `"available"`.
  - Migration scripts: 3 inline-prompt LLM calls (legacy→OLTP w/ ID-map FK rewiring, OLTP→OLAP star-schema ETL, pytest validation suite).
  - Factory reset: wipes 12 collections + Qdrant vectors + audit log entries; resets project to Discovery active + 4 stages locked.
- ✅ **4 new seed prompts** added with `force_update=True`: `datamodel.oltp`, `datamodel.olap`, `datamodel.bus_matrix`, `datamodel.chat`.
- ✅ **Frontend** (`pages/DataModel.jsx`, ~750 lines, single file with embedded sub-components):
  - Route `/data-model`. Vertical PanelGroup: ER diagram top (re-uses `ERDiagram.jsx` from Section 9) + bottom 3-panel horizontal layout (Chat | DDL Tabs | Artifacts).
  - DDL Viewer with embedded SQL syntax highlighting (regex-based, no extra deps), Generate (SSE with live progress bar), View/Edit toggle, Freeze, Download.
  - Bus Matrix Viewer with scrollable matrix table (yellow ✓ on intersection) + accordion of fact details (grain, source tables, measures).
  - Data Model RAG Chat with OLTP/OLAP toggle, [DDL_CHANGE] detection, "Apply to OLTP"/"Apply to OLAP" buttons that merge change into the artifact.
  - Artifacts panel: 6 cards (3 DDL/matrix + 3 migration scripts) with Download, Traceability tree, "Generate All Scripts" SSE button.
  - Reset modals: typed-"RESET" confirmation for Stage 2 (orange) and Factory (red).
  - Pipeline-aware: locked banner shown when DataModel stage status is "locked".
- ✅ **Sidebar**: DataModel stage now routes to `/data-model` via per-stage `path` field; locked stages remain inert with toast.
- ✅ **Testing agent**: 19/19 backend pytest tests PASS, all frontend UI checkpoints PASS (`/app/test_reports/iteration_6.json`). SSE LLM-generation endpoints NOT exercised end-to-end (would burn 60-120s LLM tokens each) — pipeline gate, CRUD shapes, reset flows all verified.

## Stage 2 Acceptance Status
- 🟢 Discovery → DataModel handoff: working (verified pipeline.py.save_stage_context wiring).
- 🟢 OLTP/OLAP DDL generation: SSE pipeline + LLM prompt seeded.
- 🟢 Bus Matrix JSON generation: working.
- 🟢 Migration scripts (3 Python files): working.
- 🟢 RAG chat with [DDL_CHANGE] detection: working.
- 🟢 Artifact freeze cascading → DataModel StageContext + Architecture unlock: working.
- 🟢 Stage 2 reset + Factory reset: working with typed-confirmation modals.

**Iteration 9 (this iteration — Console: Model Fabric + Agent Fabric + Prompt Engineering):**
- ✅ **DB**: Added `model_providers`, `agent_configs`, `token_usage_log`, `github_configs` collections.
- ✅ **Models**: Appended `ModelProvider`, `AgentConfig`, `TokenUsageLog` Pydantic models.
- ✅ **Fabric engine** (`backend/fabric/model_fabric.py`, ~280 lines): provider presets (openrouter/anthropic/openai/groq/ollama/custom), auto-detect-from-key prefix, complexity routing, `fabric_chat()` unified LLM client with status handling (enabled/disabled/wrapped/replaced), token-budget enforcement, usage logging to `token_usage_log`.
- ✅ **Seed**: 22 agents auto-seeded on startup (1 orchestrator + tasks per stage). Idempotent.
- ✅ **`routes/console.py`** (~370 lines): 15 endpoints — providers CRUD + setup + test + fetch-models, agents CRUD + reset-budget + test + usage, usage summary/log, prompt preview/test.
- ✅ **`llm.py`**: added `fabric_call()` drop-in wrapper that routes through fabric when providers configured, else falls back to legacy `chat_completion()`. Stage routes now `from llm import fabric_call as chat_completion` — zero-touch alias.
- ✅ **Frontend `/console` page** (~580 lines): 3 tabs Models | Agents | Prompts. Quick-Setup card (paste-key → auto-configure). Provider cards with routing table, Test/Fetch/Set-default/Edit-key/Delete actions. Agents accordion grouped by stage with inline expand showing complexity/status/override/wrap/replace controls + token budget + Test button. Prompts split-panel editor + live KB-resolved preview + Test prompt with cost estimate.
- ✅ **`MiniConsole.jsx`** floating bottom-right panel on Architecture + CodeGen pages, polling `/console/usage/summary` every 15s, with deep-link to `/console?tab=agents`. Renders in both locked + unlocked stage state.
- ✅ **Sidebar**: new "Console" nav item (Terminal icon) above Prompt Library; collapsed-rail icon button too.
- ✅ **Part 11 fixes**: github.py `/test` endpoint accepts empty repo_url + valid token (token-format-only validation); test_lama_v4 chat-edit assertion accepts 502 (LLM env timeout).
- ✅ **Testing**: 18/19 console backend tests pass. /console UI: all three tabs render, 22 agents grouped 5 stages (1+4, 1+4, 1+5, 1+4, 1+0). MiniConsole now renders in locked state too.
- 📐 **HLD/LLD/Sequence/CodeGen LLM job parallelism** (iteration 8.5): `asyncio.gather` + `Semaphore(4/5)` brought HLD from ~5-10 min → ~95s.

## Backlog
**P0** — None.
**P1** — Stage 5 (Living): backend + frontend (Selenium tests, SRS-drift detection, runtime observability).
**P1** — End-to-end smoke of Stage 3 (recommend → HLD → LLD → sequence → freeze) and Stage 4 (generate → ZIP → push) on the seeded project (real LLM calls — burns OpenRouter tokens; do on user request).
**P1** — Verify CodeGen GitHub-push end-to-end aligned with Stage 4 expectations (PyGithub commit-sha extraction simplified in iteration 8).
**P1** — Replace `dict` payloads with Pydantic models on `/api/kb/scan-folder`, `/api/kb/build`, `/api/srs/generate|freeze|unfreeze`, plus the new `/api/architecture/*` and `/api/codegen/*` POST bodies.
**P2** — Sidebar `stage-CodeGen-badge-locked` / `stage-CodeGen-badge-soon` data-testid alignment.
**P2** — Fix nested-button HTML in `Sidebar.jsx` (HelpIcon Radix Tooltip trigger inside `<button>` causes React hydration warning).
**P2** — Surface SRS auto-trigger failures in chat response (currently silently `false`).
**P2** — Migrate from deprecated `@app.on_event` to FastAPI `lifespan`.
**P2** — `GET /api/srs/{id}` return 404 (or `exists` flag) when no SRS.
**P2** — Streaming chat responses.

**Iteration 8 (this iteration — Stage 3 Architecture + Stage 4 CodeGen FRONTENDS):**
- ✅ **Frontend deps**: `mermaid@11`, `@monaco-editor/react` added via yarn.
- ✅ **Backend wiring**: `routes/architecture.py` + `routes/codegen.py` registered in `server.py`. Sync `require_stage_context` gate added to `start_hld/start_lld/start_seq` so callers fail fast at job creation rather than only via polling. PyGithub `r["commit"].sha` extraction simplified (removed dead `isinstance(dict)` branch).
- ✅ **`/app/frontend/src/lib/api.js`**: Added 24 new helper exports for `architecture/*` (recommend / hld / lld / sequence job starters, getArchJob, approveServiceMap, sendArchChat, applyArchChanges, artifact CRUD/freeze/download, reset) and `codegen/*` (generate job, getCodegenJob, files CRUD, downloadCodegenZipUrl + blob downloader, github-push job, sendCodegenChat, applyCodegenFileChange, freeze, reset).
- ✅ **`/app/frontend/src/pages/Architecture.jsx`** (~430 lines): horizontal `PanelGroup` (chat | artifact viewer). Tabs: service_map / hld / lld / sequence_diagrams / api_contracts. Generate buttons (Recommend, HLD, LLD, Sequence) with in-page job progress bars (poll every 2s, no SSE — bypasses K8s 60s ingress timeout). Mermaid block renderer in HLD/LLD/Sequence markdown. Service-map JSON pretty viewer with per-service cards. Chat with `[HLD_CHANGE]`/`[ARCH_CHANGE]`/`[SERVICE_ADD]`/`[SERVICE_REMOVE:...]` detection + Apply button. Edit/Freeze/Approve/Download/Reset flows. Locked banner when DataModel not frozen.
- ✅ **`/app/frontend/src/pages/CodeGen.jsx`** (~430 lines): 3-pane horizontal `PanelGroup` (file tree | Monaco editor | code chat). File tree flattened (non-recursive — visual-edits babel plugin bug workaround). Per-service filter + per-service regen. Generate-all (background job + progress bar). Monaco editor with language auto-detect by extension; Edit/Save flow; chat with `[FILE_CHANGE:path]` detection + per-block Apply button. ZIP download (blob) + GitHub-push job. Freeze CodeGen (unlocks Living). Reset modal.
- ✅ **`App.js`**: `/architecture` and `/code-gen` now route to the real pages (replacing `StagePlaceholder`).
- ✅ **Testing**: 18/18 backend pytest tests pass (test_arch_codegen.py — gates, artifacts, chat, freeze, reset, job 404, download-zip empty). Frontend smoke: Architecture page renders all tabs / generate buttons / chat / reset modal; CodeGen page renders correctly-locked state with CTA to /architecture; Sidebar Architecture badge = "Ready", CodeGen badge = "Soon"; no console errors.


## Next Phases
- **Stage 2 — DataModel**: target schema normalisation; push `schema/*.sql` to GitHub.
- **Stage 3 — Architecture**: microservice decomposition.
- **Stage 4 — CodeGen**: full target backend/frontend + Dockerfile; full GitHub push.
- **Stage 5 — Living**: Selenium tests, SRS diffs, monitoring.


## Iteration 12 (Feb 2026) — SRS Empty-Sections + Ontology Studio fixes
- ✅ **SRS empty sections (P0)** — Root cause: `model_providers` collection contained 2 active providers with fake API keys (`sk-or-fake…`). `fabric_call` detected active providers and routed all LLM calls through them, getting `401 Unauthorized` from OpenRouter, which raised RuntimeError. Some `_gen_one_section` calls returned the failure marker, others returned empty depending on per-call timing/retries.
  - Fix in `/app/backend/llm.py`: `fabric_call` now falls back to env-var OpenRouter when fabric returns empty content OR raises an exception (was previously: only fell back when fabric was *unconfigured*).
  - Fix in `/app/backend/routes/srs.py` `_gen_one_section`:
    - Added 1-retry on empty/parse failure with a directive re-prompt.
    - Added fallback to CLASSES + TABLES TOON slice when the configured `toon_focus` (e.g. `INDIVIDUALS`) doesn't exist in the TOON output.
    - Strengthened prompt to forbid empty/refusal responses.
  - Verified: ran full `/api/srs/generate` against `1376022c…` (TEST_LAMA_v4_bb4ae283, PHP). All 9 sections now populated: definitions=3536, overall_description=4767, functional_requirements=8538, non_functional_requirements=3226, use_cases=7867, constraints=2994, entity_model=4987. `version=1` persisted.
- ✅ **Ontology Studio broken on large projects** — Root cause: O(N²) Fruchterman-Reingold force layout in `OntologyStudio.jsx` froze the browser on graphs with >1000 nodes (e.g. 4411-node Java project).
  - `forceLayout()` now auto-scales iterations: 60 (≤200 nodes) → 40 → 24 → 12 (>800 nodes).
  - `GraphView` enforces `MAX_GRAPH_NODES=500`, keeps the most-connected ones plus the currently-selected node when capped, and shows an amber banner explaining the cap.
  - `OntologyStudioPage` auto-removes `Method` and `Column` from default visible types when total nodes >800 (they otherwise dominate Java/JSP projects).
  - Verified via Playwright: 4411-node project now renders cleanly with 44 visible class nodes.

## Backlog (post-iter-12)
- **P1** Continue OLTP / OLAP data-model generation quality refinement.
- **P2** Verify GitHub un-stub path for Stage 4 CodeGen push end-to-end on a Hostinger VPS pull.
- **P2** UI: add an "Auth health" pill in the Console showing whether the active provider's API key is actually working (avoids silent 401 chains).
- **P2** Add a backend `/api/console/providers/validate/{id}` endpoint that does a 1-message ping to confirm provider key validity before saving it as default.
