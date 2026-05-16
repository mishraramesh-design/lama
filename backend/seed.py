"""Seed data: prompt library + PMIS pilot project (run once on startup)."""
from datetime import datetime, timezone
import uuid

from db import projects, prompts


GLOBAL_PROMPTS = [
    {
        "key": "srs.generate",
        "stage": "Discovery",
        "description": "Generates a full IEEE 830 SRS document from KB + conversation.",
        "template": (
            "You are an IEEE 830 SRS analyst. Given this TOON knowledge base:\n{toon_context}\n"
            "and this conversation history:\n{conversation}\n"
            "Generate a complete SRS with sections:\n"
            "1-Purpose 2-Scope 3-Definitions 4-Overall Description 5-Functional Requirements "
            "6-Non-Functional Requirements 7-Use Cases 8-Constraints.\n"
            "Be specific. Use actual entity names from the KB. Do not hallucinate features.\n"
            "Return strict JSON with keys exactly: purpose, scope, definitions, overall_description, "
            "functional_requirements, non_functional_requirements, use_cases, constraints. "
            "Each value is markdown text."
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
        "key": "datamodel.optimise",
        "stage": "DataModel",
        "description": "Refactors legacy schema into normalised target schema.",
        "template": "Optimise the data model from {toon_context} targeting {target_tech}.",
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
        existing = await prompts.find_one({"key": p["key"]}, {"_id": 0})
        if not existing:
            doc = {**p, "version": 1, "updated_at": now}
            await prompts.insert_one(doc)


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
