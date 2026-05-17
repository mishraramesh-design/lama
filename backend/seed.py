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
        "template": """You are a senior PostgreSQL database architect.
Design a normalised OLTP data model migrating from a legacy system.

PROJECT: {project_name}
SOURCE: {source_tech} → TARGET: FastAPI / PostgreSQL

LEGACY SCHEMA (from KB):
{rag_context}

DOMAIN MAP:
{domain_map}

SRS FUNCTIONAL REQUIREMENTS:
{srs_functional}

RULES:
1. Apply 3NF normalisation.
2. Every table: id UUID DEFAULT gen_random_uuid() PRIMARY KEY.
3. All timestamps: TIMESTAMPTZ DEFAULT NOW().
4. Soft deletes: deleted_at TIMESTAMPTZ NULL.
5. Audit columns on every table: created_at, updated_at, created_by, updated_by.
6. FK constraints with ON DELETE RESTRICT.
7. Indexes on: all FKs, status columns, date columns.
8. ENUM types for status fields.
9. Comments on every table and complex columns.
10. Group tables: -- ===== MODULE: User Management =====
11. Minimum 80% of legacy tables represented.
12. Be exhaustive — do not truncate output.

OUTPUT: Pure PostgreSQL DDL only.
Start with: -- LAMA Generated OLTP Schema
CREATE TYPE statements first, then CREATE TABLE grouped by module,
then CREATE INDEX at end. No markdown, no explanation.""",
    },
    {
        "key": "datamodel.olap",
        "stage": "DataModel",
        "description": "Generates a star-schema OLAP data warehouse DDL optimised for BI and NLP-to-SQL.",
        "force_update": True,
        "template": """You are a senior data warehouse architect.
Design a star schema optimised for BI, visualisation, and NLP-to-SQL.

PROJECT: {project_name}
OLTP SCHEMA:
{oltp_ddl}

SRS REQUIREMENTS:
{srs_functional}

BUS MATRIX:
{bus_matrix}

RULES:
1. Star schema: fact_ and dim_ tables only.
2. Always include dim_date: date_key INT PK, full_date DATE,
   day_of_week VARCHAR, week_number INT, month_name VARCHAR,
   quarter INT, year INT, is_weekend BOOL, fiscal_year INT.
3. Surrogate keys: INT GENERATED ALWAYS AS IDENTITY on dims.
4. Fact tables: FKs to ALL relevant dimensions.
5. Measure columns: pre-aggregated amounts, counts, durations.
6. NLP-to-SQL: human-readable column names, no abbreviations,
   COMMENT ON COLUMN for every measure with unit.
7. fact tables: PARTITION BY RANGE (date_key).
8. Add 5 materialised views for the most common BI queries.

OUTPUT: Pure PostgreSQL DDL only.
Start with: -- LAMA Generated OLAP Schema (Star Schema)
Sections: -- DIMENSIONS, -- FACTS, -- MATERIALISED VIEWS""",
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
        "description": "RAG-grounded chat to refine OLTP/OLAP DDL. Wraps proposed DDL in [DDL_CHANGE] tags.",
        "force_update": True,
        "template": """You are a PostgreSQL architect helping refine a data model.

PROJECT: {project_name}
MODEL TYPE: {model_type}

CURRENT DDL:
{current_ddl}

RELEVANT KB CONTEXT:
{rag_context}

USER REQUEST: {message}

Instructions:
- Add/modify table: output ONLY the ALTER TABLE or CREATE TABLE needed.
- Question: answer concisely.
- Explanation: explain relevant DDL section only.
- Never output full schema unless explicitly asked.
- For any DDL change wrap it:
  [DDL_CHANGE]
  -- your SQL here
  [/DDL_CHANGE]""",
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
        "description": "Generates Selenium acceptance tests.",
        "template": "Write Selenium tests for the use case {use_case}.",
    },
    {
        "key": "diff.srs",
        "stage": "Living",
        "description": "Diffs two SRS versions and produces a change report.",
        "template": "Compare two SRS versions and list changes:\nA:\n{srs_a}\nB:\n{srs_b}",
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
        elif force and existing.get("version", 1) <= 2:
            # Replace stale prompts in place; keep version increment so users see the change.
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
