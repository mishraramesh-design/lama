"""Seed data: prompt library + PMIS pilot project (run once on startup)."""
from datetime import datetime, timezone
import uuid

from db import projects, prompts


GLOBAL_PROMPTS = [
    {
        "key": "srs.generate",
        "stage": "Discovery",
        "description": "Generates a full IEEE 830 SRS document (8 sections, one LLM call per section).",
        "force_update": True,
        "template": (
            "[SECTIONED GENERATION] This prompt is now driven by SECTION_CONFIGS in "
            "routes/srs.py. Each of the 8 SRS sections gets its own LLM call with a "
            "focused TOON slice (CLASSES / TABLES / ROUTES / INDIVIDUALS) and "
            "section-specific instructions enforcing min word counts, mandatory "
            "reference to real class/table/method names, and exhaustive coverage. "
            "Edit the configs in routes/srs.py SECTION_CONFIGS to change behaviour."
        ),
    },
    {
        "key": "srs.gap_question",
        "stage": "Discovery",
        "description": "Asks ONE clarifying gap question based on KB + prior questions.",
        "template": (
            "You are analysing a legacy application for migration. "
            "Project: {project_name}. KB summary: {summary}.\n"
            "TOON context (truncated):\n{toon_context}\n\n"
            "Previous questions asked:\n{asked_questions}\n\n"
            "Identify the single most important missing piece of information needed to write an accurate SRS. "
            "Ask exactly one clear question. Do not repeat previous questions. "
            "Format: plain conversational question only, no preamble."
        ),
    },
    {
        "key": "srs.edit",
        "stage": "Discovery",
        "description": "Edits an SRS section based on user instruction; preserves untouched content.",
        "force_update": True,
        "template": (
            "You are editing an IEEE 830 SRS section.\n"
            "PROJECT: {project_name}\n"
            "SECTION: {selected_section}\n\n"
            "CURRENT SECTION CONTENT:\n{current_content}\n\n"
            "RELEVANT KB CONTEXT:\n{toon_context}\n\n"
            "USER INSTRUCTION: {asked_questions}\n\n"
            "Rewrite the section incorporating the change. "
            "Preserve all existing content not mentioned in the instruction. "
            "Continue FR-IDs from the highest existing number. "
            "Reference real class/table/method names from the KB. "
            "Return ONLY the updated markdown for this section. No preamble. No code fences."
        ),
    },
    {
        "key": "datamodel.optimise",
        "stage": "DataModel",
        "description": "Refactors legacy schema into normalised target schema.",
        "template": "Optimise the data model from {toon_context} targeting {target_tech}.",
    },
    {
        "key": "datamodel.oltp",
        "stage": "DataModel",
        "description": "Generates normalised 3NF PostgreSQL OLTP DDL from legacy schema + SRS functional requirements.",
        "force_update": True,
        "template": """You are a senior PostgreSQL database architect designing a 3NF OLTP schema.
You will be HARSHLY PENALISED for missing tables, missing FK constraints, denormalised
columns, or VARCHAR-everything types. Aim for PRODUCTION-READY DDL.

PROJECT: {project_name}
SOURCE: {source_tech} → TARGET: FastAPI / PostgreSQL

LEGACY SCHEMA (from KB):
{rag_context}

DOMAIN MAP:
{domain_map}

SRS FUNCTIONAL REQUIREMENTS (your DDL must support EVERY one):
{srs_functional}

═══════════════════════════════════════════════════════════════════
COMPLETENESS CHECKLIST — DO NOT FINISH BEFORE TICKING EVERY ITEM
═══════════════════════════════════════════════════════════════════
□ Every entity mentioned in the SRS Functional section has a corresponding table.
□ Every legacy table from the RAG context has been carried over (or explicitly
  merged with a `-- MERGED FROM: old_table_x` comment).
□ Every FK column declared with REFERENCES ... ON DELETE ...
□ Every status / state column has its own ENUM TYPE.
□ Every junction (M:N) table has a UNIQUE(a_id, b_id) constraint.
□ Every monetary amount uses NUMERIC(18,4), never FLOAT or VARCHAR.
□ Every email/url/code field has a CHECK constraint (regex or length).

═══════════════════════════════════════════════════════════════════
HARD RULES
═══════════════════════════════════════════════════════════════════
1. Normalisation: 3NF strict. No repeating groups, no transitive deps.
2. Every table:
     id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
     created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
     updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
     created_by    UUID REFERENCES users(id) ON DELETE SET NULL,
     updated_by    UUID REFERENCES users(id) ON DELETE SET NULL,
     deleted_at    TIMESTAMPTZ NULL
3. Data types — be explicit:
     - Money / quantity → NUMERIC(p,s) with explicit precision
     - Booleans → BOOLEAN, never SMALLINT
     - Dates → DATE, timestamps → TIMESTAMPTZ
     - Long text → TEXT, short codes → VARCHAR(n)
     - JSON payloads → JSONB (never JSON)
     - IDs → UUID
4. Foreign keys: ON DELETE RESTRICT (default) or CASCADE for child rows.
   Always add an INDEX on every FK column.
5. ENUM types for: order_status, payment_status, user_role, etc.
   Declare BEFORE any CREATE TABLE that uses them.
6. Indexes:
     - btree on every FK column
     - btree on every status/state column
     - btree on every "queried by date" column (created_at, transaction_date, …)
     - partial UNIQUE on `WHERE deleted_at IS NULL` for soft-delete uniqueness
7. CHECK constraints: amount >= 0, percentage BETWEEN 0 AND 100, email regex,
   non-empty TEXT NOT NULL columns.
8. COMMENT ON TABLE / COMMENT ON COLUMN — every table and every non-obvious column.
9. Group tables: -- ===== MODULE: <DomainName> =====
10. SRS COVERAGE COMMENT: after each table add
      -- COVERS: SRS-FR-XX, SRS-FR-YY  (cite the requirement IDs the table satisfies)

OUTPUT (no markdown, no fences, no prose):
-- LAMA Generated OLTP Schema
-- Covers SRS functional requirements: <list FR ids>
<CREATE EXTENSION statements: pgcrypto, citext>
<CREATE TYPE …> (all enums)
-- ===== MODULE: <ModuleName> =====
<CREATE TABLE …>
…
-- ===== INDEXES =====
<CREATE INDEX …>
-- ===== VIEWS =====
<CREATE VIEW …>  (helper views for common joins, optional)""",
    },
    {
        "key": "datamodel.olap",
        "stage": "DataModel",
        "description": "Generates a star-schema OLAP data warehouse DDL optimised for BI and NLP-to-SQL.",
        "force_update": True,
        "template": """You are a senior data warehouse architect designing a Kimball star schema.
You will be HARSHLY PENALISED for snowflaked dimensions, fact tables without a
date FK, measures stored as VARCHAR, or dimensions without surrogate keys.

PROJECT: {project_name}
OLTP SCHEMA (source of truth):
{oltp_ddl}

SRS REQUIREMENTS (analytical questions to answer):
{srs_functional}

BUS MATRIX (facts × dimensions plan):
{bus_matrix}

═══════════════════════════════════════════════════════════════════
COMPLETENESS CHECKLIST
═══════════════════════════════════════════════════════════════════
□ For every fact in the bus matrix → one fact_ table.
□ For every dim in the bus matrix → one dim_ table.
□ Every fact has FKs to dim_date AND every applicable dim_ (no orphaned facts).
□ Every dimension has a stated grain in `COMMENT ON TABLE`.
□ Every fact has a stated grain in `COMMENT ON TABLE` (e.g. "one row per
  order_line per day per store").
□ Every numeric measure has explicit PRECISION + SCALE + unit comment.

═══════════════════════════════════════════════════════════════════
HARD RULES
═══════════════════════════════════════════════════════════════════
1. STAR SCHEMA strict — NO snowflaking. Flatten hierarchies into dimension
   attributes (e.g. dim_product.category_name not dim_category.name).
2. Dimensions:
     <dim>_key  INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
     <natural_key> ...
     SCD Type-2 columns where history matters:
       valid_from DATE, valid_to DATE NULL, is_current BOOLEAN
3. Facts:
     <fact>_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
     <dim>_key    INT NOT NULL REFERENCES dim_<x>(<dim>_key),
     date_key     INT NOT NULL REFERENCES dim_date(date_key),
     <measures>   NUMERIC(p,s) NOT NULL DEFAULT 0,
     loaded_at    TIMESTAMPTZ DEFAULT NOW()
4. dim_date (mandatory, fully populated):
     date_key INT PK, full_date DATE NOT NULL UNIQUE,
     day_of_week VARCHAR(10), day_of_month INT, week_number INT,
     month_number INT, month_name VARCHAR(10), quarter INT, year INT,
     is_weekend BOOLEAN, is_holiday BOOLEAN, fiscal_year INT, fiscal_quarter INT
5. NLP-to-SQL friendly:
     - Column names in plain English (total_amount_inr, order_count, days_to_ship)
     - COMMENT ON COLUMN with measurement unit ("INR", "count", "days")
     - No cryptic abbreviations (use `customer_id` not `cstm_id`)
6. Partitioning: every fact table PARTITION BY RANGE(date_key) by year.
   Create at least 3 partitions (last year, current year, next year).
7. Indexes:
     - btree on every <dim>_key in fact tables (composite covers common joins)
     - btree on date_key, customer_key, product_key composites where used
     - BRIN index on loaded_at (cheap, time-series-friendly)
8. Materialised views — produce 5 covering the most likely BI questions
   from SRS. Each must:
     - Be named mv_<question_slug>
     - Have a comment describing the BI question it answers
     - REFRESH MATERIALIZED VIEW CONCURRENTLY-compatible (UNIQUE index)
9. Provide one `CREATE PROCEDURE refresh_olap_all()` that refreshes all MVs.

OUTPUT (pure PostgreSQL DDL, no markdown):
-- LAMA Generated OLAP Schema (Star, Kimball-style)
-- Covers SRS analytical requirements: <list>
-- ===== DIMENSIONS =====
<CREATE TABLE dim_…> (dim_date first, then alphabetical)
-- ===== FACTS =====
<CREATE TABLE fact_… PARTITION BY RANGE(date_key)>
<CREATE TABLE fact_…_y2024 PARTITION OF fact_… FOR VALUES FROM (20240101) TO (20250101)>
-- ===== INDEXES =====
<CREATE INDEX …>
-- ===== MATERIALISED VIEWS =====
<CREATE MATERIALIZED VIEW mv_… AS SELECT …>
<CREATE UNIQUE INDEX ON mv_…>
-- ===== REFRESH PROCEDURE =====
<CREATE OR REPLACE PROCEDURE refresh_olap_all() AS …>""",
    },
    {
        "key": "datamodel.bus_matrix",
        "stage": "DataModel",
        "description": "Generates a Kimball Bus Matrix (facts × dimensions) as strict JSON.",
        "force_update": True,
        "template": """You are a BI architect. Create a Bus Matrix.

PROJECT: {project_name}
OLTP SCHEMA:
{oltp_ddl}

SRS USE CASES:
{srs_use_cases}

Return STRICT JSON only, no markdown:
{{
  "facts": [
    {{
      "name": "fact_xxx",
      "grain": "one row per ...",
      "source_tables": ["table1"],
      "measures": [
        {{"name": "amount", "type": "DECIMAL", "agg": "SUM"}}
      ]
    }}
  ],
  "dimensions": [
    {{
      "name": "dim_xxx",
      "source_tables": ["table1"],
      "attributes": [
        {{"name": "attr_name", "type": "VARCHAR"}}
      ]
    }}
  ],
  "matrix": {{
    "fact_xxx": {{"dim_xxx": true, "dim_date": true}}
  }}
}}""",
    },
    {
        "key": "datamodel.chat",
        "stage": "DataModel",
        "description": "RAG-grounded chat to refine OLTP/OLAP/Bus-Matrix/ER. Wraps proposed change in [DDL_CHANGE]/[BUS_CHANGE]/[ER_CHANGE] tags.",
        "force_update": True,
        "template": """You are a PostgreSQL data architect helping refine a data model.

PROJECT: {project_name}
MODEL TYPE: {model_type}   (OLTP | OLAP | BUS | ER)

CURRENT ARTIFACT:
{current_ddl}

RELEVANT KB CONTEXT:
{rag_context}

USER REQUEST: {message}

INSTRUCTIONS
- Explain briefly what you propose (max ~5 lines), then wrap the actionable change.
- Choose the correct wrapper based on MODEL TYPE:
    * OLTP / OLAP  → wrap raw SQL DDL in [DDL_CHANGE] … [/DDL_CHANGE]
    * BUS          → wrap a complete JSON object that REPLACES the bus matrix in
                     [BUS_CHANGE] … [/BUS_CHANGE]  (shape: {{"facts":[…],"dimensions":[…]}})
    * ER           → wrap a JSON patch in [ER_CHANGE] … [/ER_CHANGE]  with shape
                     {{"add_edges":[{{"from_table":"a","from_col":"b","to_table":"c"}}],
                       "remove_edges":[{{"from_table":"a","from_col":"b","to_table":"c"}}]}}
- For pure Q&A / explanation just answer; omit the wrapper.
- For DDL: only output ALTER TABLE or focused CREATE TABLE, never the whole schema.
- Use real names from CURRENT ARTIFACT and KB CONTEXT. Never invent placeholders.""",
    },
    # ---------- Stage 3 — Architecture ----------
    {
        "key": "arch.recommend",
        "stage": "Architecture",
        "description": "Analyses SRS + OLTP + module map; recommends architecture pattern and decomposes into services. Returns strict JSON.",
        "force_update": True,
        "template": """You are a senior software architect analysing a legacy application for migration.

PROJECT: {project_name}
SOURCE: {source_tech} → TARGET: React frontend + {backend_lang} backend + PostgreSQL

SRS SUMMARY:
{srs_summary}

OLTP SCHEMA SUMMARY:
{oltp_summary}

MODULE STRUCTURE:
{module_context}

COMPLEXITY SIGNALS:
{complexity_signals}

RELEVANT KB CONTEXT:
{rag_context}

TASK: Recommend the best architecture pattern and decompose into services.

RULES:
- Never recommend microservices for simple apps (<50 tables, <5 modules).
- Modular monolith is valid and often better for medium complexity.
- Every service must have a clear single responsibility.
- Use actual module and table names from the KB — never generic names.
- backend_lang must be one of: nodejs | python | java | go.
- Default backend_lang: nodejs (override only if Java/Spring detected in source).

Return STRICT JSON ONLY. No markdown fences. Schema:
{{
  "recommended_pattern": "microservices|modular_monolith|monolith",
  "reasoning": "...",
  "complexity_score": 0,
  "services": [
    {{
      "name": "kebab-case-service-name",
      "display_name": "Human Readable Name",
      "responsibility": "one sentence",
      "tables": ["table1", "table2"],
      "api_endpoints": ["POST /resource", "GET /resource/:id"],
      "dependencies": ["other-service-name"],
      "events_published": [],
      "events_consumed": [],
      "backend_lang": "nodejs",
      "estimated_loc": 500
    }}
  ],
  "frontend_service": {{
    "name": "frontend",
    "framework": "react",
    "pages": ["PageName"],
    "api_consumers": ["service-name"]
  }},
  "shared_services": ["auth", "notification"],
  "event_bus": false,
  "api_gateway": true,
  "rationale": "..."
}}""",
    },
    {
        "key": "arch.hld",
        "stage": "Architecture",
        "description": "Generates a single section of the High Level Design document.",
        "force_update": True,
        "template": """You are writing a High Level Design (HLD) document.

PROJECT: {project_name}
PATTERN: {recommended_pattern}
SERVICES: {services_summary}
SRS FUNCTIONAL REQUIREMENTS: {srs_functional}
OLTP SCHEMA: {oltp_summary}

Write the "{section_name}" section of the HLD.

{section_instructions}

RULES:
- Use actual service names, table names, endpoint paths.
- All diagrams must be valid Mermaid syntax inside ```mermaid fences.
- Sequence diagrams: use sequenceDiagram notation.
- Class diagrams: use classDiagram notation.
- C4 context: use C4Context notation.
- Deployment: use graph LR notation.
- Minimum {min_words} words.
- No placeholder text — every detail must reference real entities.
- Format: markdown with ## sub-headings.

Return only the markdown for this section. No preamble.""",
    },
    {
        "key": "arch.lld",
        "stage": "Architecture",
        "description": "Generates Low Level Design markdown for a single service.",
        "force_update": True,
        "template": """You are writing the Low Level Design for one service.

PROJECT: {project_name}
SERVICE: {service_name} ({service_responsibility})
BACKEND: {backend_lang}
TABLES OWNED: {service_tables}
API ENDPOINTS: {service_endpoints}
DEPENDENCIES: {service_dependencies}
HLD CONTEXT: {hld_summary}
OLTP DDL (relevant tables): {relevant_ddl}

Write a complete LLD for this service covering:
1. Class/Module diagram (Mermaid classDiagram).
2. Method signatures (params, returns, JSDoc/docstring style).
3. Database design for this service (tables, indexes, constraints).
4. API specification (OpenAPI 3.0 YAML inside ```yaml fences).
5. Error handling strategy (codes, retry, circuit breaker).
6. Test strategy (unit + integration scenarios).

RULES:
- Use actual column names from the OLTP DDL.
- Be exhaustive — a developer must implement from this alone.
- Never use generic names like "doSomething" or "handleRequest".

Return markdown only. No preamble.""",
    },
    {
        "key": "arch.sequence",
        "stage": "Architecture",
        "description": "Mermaid sequenceDiagram for one workflow.",
        "force_update": True,
        "template": """You are creating a Mermaid sequence diagram for one key workflow.

PROJECT: {project_name}
WORKFLOW: {use_case_name}
USE CASE: {use_case_content}
SERVICES: {services_list}
RELEVANT ENDPOINTS: {relevant_endpoints}

Create a detailed Mermaid sequenceDiagram showing:
- All actors (user roles from SRS).
- All service-to-service calls.
- Database interactions.
- Async events if applicable.
- Error / rejection paths as alt blocks.
- Authentication checks.

Use actual service names, endpoint paths, DB table names.

Return ONLY the mermaid block:
```mermaid
sequenceDiagram
...
```
No explanation. No preamble.""",
    },
    {
        "key": "arch.chat",
        "stage": "Architecture",
        "description": "RAG-grounded architecture refinement chat. Emits change markers.",
        "force_update": True,
        "template": """You are an architecture consultant reviewing a design.

PROJECT: {project_name}
CURRENT ARCHITECTURE:
{arch_context}

RELEVANT KB CONTEXT:
{rag_context}

USER REQUEST: {message}

Instructions:
- Answer architecture questions directly and concisely.
- For changes wrap modified content in change markers:
  [HLD_CHANGE:section_name] ...updated markdown... [/HLD_CHANGE]
  [ARCH_CHANGE:service_name] ...updated service definition JSON... [/ARCH_CHANGE]
  [SERVICE_ADD] ...service definition JSON... [/SERVICE_ADD]
  [SERVICE_REMOVE:service_name]
- Only output change markers when the user is requesting a change.
- Keep changes minimal and targeted.
- Always explain your reasoning before the change markers.""",
    },
    # ---------- Stage 4 — Code Generation ----------
    {
        "key": "codegen.service",
        "stage": "CodeGen",
        "description": "Generates a single backend service file (route/model/service/middleware/dockerfile/test).",
        "force_update": True,
        "template": """You are a senior {backend_lang} developer.
Generate production-ready code for one microservice/module.

PROJECT: {project_name}
SERVICE: {service_name} ({service_responsibility})
BACKEND: {backend_lang}
DATABASE: PostgreSQL

LLD FOR THIS SERVICE:
{service_lld}

OLTP DDL (this service's tables):
{service_ddl}

API ENDPOINTS TO IMPLEMENT:
{service_endpoints}

DEPENDENCIES ON OTHER SERVICES:
{service_dependencies}

Generate the "{file_type}" file at path "{file_path}".

File-type specific instructions:
{file_type_instructions}

CRITICAL RULES:
- Every function/class must have JSDoc (JS/TS) or docstrings (Python/Java/Go).
- Use async/await — no callbacks.
- Validate ALL inputs.
- Use parameterised queries — never string-interpolated SQL.
- Return standardised error responses: {{"error": true, "code": "E001", "message": "..."}}.
- Include logging at entry/exit of every route handler.
- No hardcoded credentials — use environment variables.
- Node.js: Express 5 or Fastify 4.
- Python: FastAPI + SQLAlchemy 2.0.
- Java: Spring Boot 3 + JPA.
- Go: Gin + GORM.

Return ONLY the file content. No preamble. No markdown fences.""",
    },
    {
        "key": "codegen.frontend",
        "stage": "CodeGen",
        "description": "Generates a single React frontend file.",
        "force_update": True,
        "template": """You are a senior React + TypeScript developer.

PROJECT: {project_name}
COMPONENT TYPE: {component_type}
FILE PATH: {file_path}
AVAILABLE API SERVICES: {api_summary}
RELEVANT SRS USE CASES: {relevant_use_cases}

Generate the "{file_path}" file.

{component_instructions}

RULES:
- TypeScript strictly typed — no any.
- Functional components with hooks only.
- React Query for data fetching, Zustand for global state.
- Tailwind CSS for styling.
- Accessible (aria labels, keyboard nav). Responsive (mobile-first).
- Always handle loading + error + empty states.
- Tests use Vitest + React Testing Library.

Return ONLY the file content. No preamble. No markdown fences.""",
    },
    {
        "key": "codegen.chat",
        "stage": "CodeGen",
        "description": "RAG-grounded code refinement chat. Emits [FILE_CHANGE:path] markers with full updated file content.",
        "force_update": True,
        "template": """You are reviewing generated application code.

PROJECT: {project_name}
TARGET FILE: {file_path}
CURRENT CONTENT:
{current_content}

RELATED FILES CONTEXT:
{related_context}

RELEVANT KB CONTEXT:
{rag_context}

USER REQUEST: {message}

Instructions:
- For code changes wrap in:
  [FILE_CHANGE:{file_path}]
  ...complete updated file content...
  [/FILE_CHANGE]
- Only output the complete file — never partial snippets.
- Explain what changed and why before the change marker.
- If the change affects other files, mention them specifically.
- Never break existing interfaces.""",
    },
    {
        "key": "codegen.docs",
        "stage": "CodeGen",
        "description": "Generates README/API_REFERENCE/ARCHITECTURE markdown docs.",
        "force_update": True,
        "template": """You are writing technical documentation.

PROJECT: {project_name}
SERVICE: {service_name}
DOC TYPE: {doc_type}
SERVICE LLD: {service_lld}
GENERATED FILES: {file_list}

Write the {doc_type} documentation for this service.

For service README.md include:
- Overview and responsibility.
- Tech stack and dependencies.
- Setup and running locally.
- Environment variables (table).
- API endpoints summary (table).
- Database tables owned (list).
- Events published/consumed.
- Testing instructions.
- Deployment notes.

Return markdown only. No preamble.""",
    },
    {
        "key": "arch.decompose",
        "stage": "Architecture",
        "description": "Decomposes the legacy monolith into target microservices.",
        "template": "Decompose the system in {toon_context} into microservices for {target_tech}.",
    },
    {
        "key": "code.generate",
        "stage": "CodeGen",
        "description": "Generates target code for a chosen module.",
        "template": "Generate {target_tech} code for module {module} using context: {toon_context}.",
    },
    {
        "key": "test.unit",
        "stage": "CodeGen",
        "description": "Generates unit tests for the generated module.",
        "template": "Write unit tests for module {module} ({target_tech}).",
    },
    {
        "key": "test.selenium",
        "stage": "Living",
        "force_update": True,
        "description": "Generates Selenium acceptance tests.",
        "template": """You are a senior QA automation engineer.
Generate Selenium WebDriver acceptance tests in JAVA + JUnit 5 for the use cases below.

PROJECT: {project_name}
TARGET STACK: {target_tech}

USE CASES (from SRS):
{use_cases}

API CONTRACTS / ROUTES (from architecture):
{routes}

═════════════════════════════════════════════════════════════════
HARD RULES — production-quality test code only
═════════════════════════════════════════════════════════════════
1. One Java class per use case, named <UseCaseName>Test (PascalCase).
2. Use Page Object Model — create a separate <PageName>Page.java for each
   distinct screen, with `@FindBy` locators and action methods.
3. Use JUnit 5 (`@Test`, `@BeforeAll`, `@AfterEach`), AssertJ for fluent
   assertions, and WebDriverManager for driver bootstrap.
4. Every test must:
   - Set up an isolated browser session.
   - Use explicit waits (WebDriverWait) — NEVER Thread.sleep.
   - Take a screenshot on failure (use `@ExtendWith(ScreenshotExtension.class)`).
   - Assert at least one positive AND one negative scenario.
5. Group by module: package com.lama.tests.<module_slug>.
6. Add Javadoc on every test method linking back to SRS-UC-XX.

OUTPUT — pure code, NO markdown fences. Use this exact layout, one file per
class, prefixed by an `=== FILE: <relative_path> ===` marker so the runtime
can split the response into individual files:

=== FILE: src/test/java/com/lama/tests/auth/LoginTest.java ===
package com.lama.tests.auth;
...
=== FILE: src/test/java/com/lama/tests/auth/LoginPage.java ===
...""",
    },
    {
        "key": "test.jmeter",
        "stage": "Living",
        "force_update": True,
        "description": "Generates Apache JMeter performance test plans (.jmx).",
        "template": """You are a senior performance engineer.
Generate an Apache JMeter test plan (.jmx — XML) that exercises the production
API endpoints under realistic load.

PROJECT: {project_name}
BASE URL: {base_url}
API ENDPOINTS (verb + path, from architecture):
{endpoints}

NON-FUNCTIONAL TARGETS (from SRS):
{nfr_summary}

═════════════════════════════════════════════════════════════════
HARD RULES
═════════════════════════════════════════════════════════════════
1. ONE master Test Plan (`jmeterTestPlan version="1.2"`) per response.
2. Thread Groups by user persona:
   - Anonymous (browse/health) — 20 users, 60s ramp
   - Authenticated (CRUD) — 50 users, 120s ramp
   - Admin (heavy queries) — 5 users, 30s ramp
3. Each request:
   - HTTPSampler with method + path + body (parameterised via CSV Data Set)
   - Header Manager with `Content-Type: application/json` + `Authorization`
   - Response Assertion (200/201/204 — adjust per verb)
   - Duration Assertion ≤ 1500ms for GETs, ≤ 3000ms for writes
4. Insert a CSV Data Set Config that points to `test-data/<endpoint>_data.csv`
   so the .jmx is dataset-driven (no hardcoded payloads).
5. Listeners (DISABLED by default for CI):
   - Summary Report
   - Aggregate Report
   - Backend Listener for InfluxDB/Grafana
6. Plugin requirements at top of file in a `<!-- requires: -->` comment block:
   jmeter-plugins-graphs-basic, jmeter-plugins-cmd, jmeter-plugins-casutg.

OUTPUT — pure XML, NO markdown, one file per response. Begin with:
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">
...
</jmeterTestPlan>""",
    },
    {
        "key": "drift.detector",
        "stage": "Living",
        "force_update": True,
        "description": "Detects drift between the frozen SRS and the live deployed application.",
        "template": """You are a senior software architect doing a drift audit.
Compare the frozen SRS (source of truth) against signals collected from the
running system (logs, telemetry, schema introspection). Report ONLY observable
gaps with severity classification.

SRS FUNCTIONAL REQUIREMENTS:
{srs_functional}

CURRENT SYSTEM SIGNALS (live):
{live_signals}

OUTPUT — markdown report with these EXACT sections:
## Drift Summary
- N requirements covered fully
- N requirements partially covered
- N requirements missing

## Critical Drift (P0)
| SRS-FR | Expected | Observed | Recommended action |
| --- | --- | --- | --- |
...

## Major Drift (P1)
...

## Minor Drift (P2)
...

## Recommendations
1. ...

Be ruthless and specific. Cite the exact SRS-FR-XX id on every row.""",
    },
    {
        "key": "diff.srs",
        "stage": "Living",
        "force_update": True,
        "description": "Diffs two SRS versions and produces a change report.",
        "template": """Compare two SRS versions and produce a precise change report.

OLD (Version A):
{srs_a}

NEW (Version B):
{srs_b}

OUTPUT — markdown:
## Added
- Section, Requirement-ID, summary
## Removed
- ...
## Modified
- ...
## Impact Assessment
- Which downstream artifacts (data model, code, tests) need regeneration?
""",
    },
]


async def seed_prompts():
    now = datetime.now(timezone.utc).isoformat()
    for p in GLOBAL_PROMPTS:
        force = p.pop("force_update", False)
        existing = await prompts.find_one({"key": p["key"]}, {"_id": 0})
        if not existing:
            doc = {**p, "version": 1, "updated_at": now}
            await prompts.insert_one(doc)
        elif force:
            # Replace in place if the stored template differs from the seed.
            if (existing.get("template") or "") != p.get("template", ""):
                await prompts.update_one(
                    {"key": p["key"]},
                    {"$set": {**p, "version": existing.get("version", 1) + 1, "updated_at": now}},
                )


async def seed_pilot_project():
    count = await projects.count_documents({})
    if count > 0:
        return None
    now = datetime.now(timezone.utc).isoformat()
    pilot = {
        "id": str(uuid.uuid4()),
        "name": "PMIS Migration Pilot",
        "source_tech": "PHP 8 / CodeIgniter 4 / MariaDB",
        "target_tech": "FastAPI / Python 3.12 / PostgreSQL",
        "description": "LAMA pilot — PHP 8 / CodeIgniter 4 / MariaDB monolith migrating to FastAPI / Python 3.12 / PostgreSQL",
        "github_repo": "",
        "stage": "Discovery",
        "stage_status": {
            "Discovery": "active",
            "DataModel": "locked",
            "Architecture": "locked",
            "CodeGen": "locked",
            "Living": "locked",
        },
        "freeze_gates": {},
        "created_at": now,
        "updated_at": now,
    }
    await projects.insert_one(pilot)
    return pilot


async def seed_agents():
    """Seed default agent configurations. Idempotent."""
    from db import agent_configs as ac_col
    from models import AgentConfig as _AgentConfig
    AGENTS = [
        # Orchestrators
        {"key": "orchestrator.discovery", "agent_type": "orchestrator", "stage": "Discovery",
         "label": "Discovery Orchestrator", "description": "Manages KB build → OWL → TOON → SRS pipeline.",
         "complexity": "medium", "max_tokens": 2048},
        {"key": "orchestrator.datamodel", "agent_type": "orchestrator", "stage": "DataModel",
         "label": "Data Model Orchestrator", "description": "Manages OLTP → OLAP → Bus Matrix → Scripts.",
         "complexity": "medium", "max_tokens": 2048},
        {"key": "orchestrator.architecture", "agent_type": "orchestrator", "stage": "Architecture",
         "label": "Architecture Orchestrator", "description": "Manages Recommend → HLD → LLD → Sequence.",
         "complexity": "medium", "max_tokens": 2048},
        {"key": "orchestrator.codegen", "agent_type": "orchestrator", "stage": "CodeGen",
         "label": "CodeGen Orchestrator", "description": "Manages per-service file generation pipeline.",
         "complexity": "medium", "max_tokens": 2048},
        {"key": "orchestrator.living", "agent_type": "orchestrator", "stage": "Living",
         "label": "Living SRS Orchestrator", "description": "Manages diff SRS → test generation pipeline.",
         "complexity": "medium", "max_tokens": 2048},
        # Living
        {"key": "test.selenium", "agent_type": "task", "stage": "Living",
         "label": "Selenium Test Generator", "description": "Generates JUnit5 + Selenium acceptance tests for each use case.",
         "complexity": "medium", "max_tokens": 6000},
        {"key": "test.jmeter", "agent_type": "task", "stage": "Living",
         "label": "JMeter Plan Generator", "description": "Generates Apache JMeter (.jmx) performance test plans per persona.",
         "complexity": "medium", "max_tokens": 8000},
        {"key": "drift.detector", "agent_type": "task", "stage": "Living",
         "label": "Drift Detector", "description": "Compares frozen SRS against live signals and reports gaps.",
         "complexity": "high", "max_tokens": 5000},
        {"key": "diff.srs", "agent_type": "task", "stage": "Living",
         "label": "SRS Diff", "description": "Diffs two SRS snapshots and proposes which artifacts to regenerate.",
         "complexity": "medium", "max_tokens": 4000},
        # Discovery
        {"key": "srs.gap_question", "agent_type": "task", "stage": "Discovery",
         "label": "SRS Gap Questioner", "description": "Asks one clarifying question per turn from KB.",
         "complexity": "low", "max_tokens": 512},
        {"key": "srs.generate", "agent_type": "task", "stage": "Discovery",
         "label": "SRS Generator", "description": "Generates one IEEE 830 SRS section per call.",
         "complexity": "high", "max_tokens": 8000},
        {"key": "srs.edit", "agent_type": "task", "stage": "Discovery",
         "label": "SRS Editor", "description": "Edits one SRS section per user instruction.",
         "complexity": "medium", "max_tokens": 6000},
        {"key": "srs.diff", "agent_type": "task", "stage": "Discovery",
         "label": "SRS Diff Analyser", "description": "Diff frozen SRS vs running system.",
         "complexity": "medium", "max_tokens": 4000},
        # DataModel
        {"key": "datamodel.oltp", "agent_type": "task", "stage": "DataModel",
         "label": "OLTP DDL Generator", "description": "Generates normalised PostgreSQL OLTP schema.",
         "complexity": "high", "max_tokens": 16000},
        {"key": "datamodel.olap", "agent_type": "task", "stage": "DataModel",
         "label": "OLAP Schema Generator", "description": "Generates star schema for BI/NLP-to-SQL.",
         "complexity": "medium", "max_tokens": 14000},
        {"key": "datamodel.bus_matrix", "agent_type": "task", "stage": "DataModel",
         "label": "Bus Matrix Generator", "description": "Generates fact × dimension bus matrix JSON.",
         "complexity": "low", "max_tokens": 4000},
        {"key": "datamodel.chat", "agent_type": "task", "stage": "DataModel",
         "label": "Data Model Chat", "description": "RAG chat for editing OLTP/OLAP models.",
         "complexity": "medium", "max_tokens": 6000},
        # Architecture
        {"key": "arch.recommend", "agent_type": "task", "stage": "Architecture",
         "label": "Architecture Recommender", "description": "Recommends pattern and service decomposition.",
         "complexity": "high", "max_tokens": 8000},
        {"key": "arch.hld", "agent_type": "task", "stage": "Architecture",
         "label": "HLD Generator", "description": "Generates one HLD section per call.",
         "complexity": "high", "max_tokens": 4000},
        {"key": "arch.lld", "agent_type": "task", "stage": "Architecture",
         "label": "LLD Generator", "description": "Generates complete LLD for one service.",
         "complexity": "medium", "max_tokens": 6000},
        {"key": "arch.sequence", "agent_type": "task", "stage": "Architecture",
         "label": "Sequence Diagram Generator", "description": "Generates Mermaid sequence diagrams per use case.",
         "complexity": "low", "max_tokens": 2500},
        {"key": "arch.chat", "agent_type": "task", "stage": "Architecture",
         "label": "Architecture Chat", "description": "RAG chat for editing architecture documents.",
         "complexity": "medium", "max_tokens": 4000},
        # CodeGen
        {"key": "codegen.service", "agent_type": "task", "stage": "CodeGen",
         "label": "Service Code Generator", "description": "Generates one production code file per call.",
         "complexity": "high", "max_tokens": 4500},
        {"key": "codegen.frontend", "agent_type": "task", "stage": "CodeGen",
         "label": "Frontend Code Generator", "description": "Generates React components and pages.",
         "complexity": "medium", "max_tokens": 4500},
        {"key": "codegen.docs", "agent_type": "task", "stage": "CodeGen",
         "label": "Documentation Generator", "description": "Generates service README and API docs.",
         "complexity": "low", "max_tokens": 4000},
        {"key": "codegen.chat", "agent_type": "task", "stage": "CodeGen",
         "label": "CodeGen Chat", "description": "RAG chat for editing generated code files.",
         "complexity": "medium", "max_tokens": 6000},
    ]
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    for a in AGENTS:
        existing = await ac_col.find_one({"key": a["key"]}, {"_id": 0})
        if not existing:
            doc = _AgentConfig(**a)
            d = doc.model_dump()
            d["created_at"] = now
            d["updated_at"] = now
            await ac_col.insert_one(d)


async def run_seed():
    await seed_prompts()
    await seed_pilot_project()
    await seed_agents()
