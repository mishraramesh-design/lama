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


async def run_seed():
    await seed_prompts()
    await seed_pilot_project()
