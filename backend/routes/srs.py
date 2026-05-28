"""SRS generation, retrieval, freeze, section edit."""
import io
import json
import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone

from db import srs_documents, kb_toon, messages, projects, audit_log, prompts, project_prompts, kb_entities, stage_context as stage_context_col
from models import SRSDocument, SRSSectionUpdate, StageContext
from llm import fabric_call as chat_completion
from kb.vector_store import search as qdrant_search
from kb.owl_export import export_owl
from kb.toon import serialise as toon_serialise


SECTION_QUERIES = {
    "purpose": "system purpose user roles business modules controllers",
    "scope": "controllers modules features endpoints functions",
    "definitions": "roles acronyms terminology domain names",
    "overall_description": "architecture tables relationships users sessions",
    "functional_requirements": "CRUD workflow approval status calculation",
    "non_functional_requirements": "performance security audit log uptime",
    "use_cases": "workflow approval submission upload user journey",
    "constraints": "foreign keys dependencies integrations external API",
}

router = APIRouter(prefix="/srs", tags=["srs"])


# ----------------------------------------------------------------------------
# Section configs — one LLM call per section, each with a focused TOON slice.
# ----------------------------------------------------------------------------
SECTION_CONFIGS = [
    {
        "key": "purpose",
        "label": "1. Purpose",
        "toon_focus": "CLASSES",
        "min_words": 300,
        "instructions": """Write a comprehensive Purpose section covering:
- What this system does (based on actual controller/model names found)
- Who the primary users are (list actual roles from KB)
- What business problems it solves
- What the migration aims to achieve
- List every major module identified (name each controller group)
- Business context and regulatory requirements visible in the code""",
    },
    {
        "key": "scope",
        "label": "2. Scope",
        "toon_focus": "CLASSES",
        "min_words": 400,
        "instructions": """Write a detailed Scope section covering:
- List EVERY functional module found (group controllers by domain)
- For each module: what it does, which classes implement it
- What is explicitly OUT of scope for this migration
- Integration boundaries (external APIs, third-party systems found)
- Data scope: list major table groups by domain""",
    },
    {
        "key": "definitions",
        "label": "3. Definitions, Acronyms & Abbreviations",
        "toon_focus": "INDIVIDUALS",
        "min_words": 200,
        "instructions": """Define every domain term, acronym, and abbreviation found in:
- Table names and column names
- Class names and method names
- Role names from the KB
- Any government/regulatory terms visible
Format as a definition list with term: explanation.""",
    },
    {
        "key": "overall_description",
        "label": "4. Overall Description",
        "toon_focus": "TABLES",
        "min_words": 500,
        "instructions": """Write a comprehensive system description covering:
- System architecture (monolith structure based on controller/model pattern)
- User classes and roles (list every role with their permissions)
- Operating environment (PHP version, DB, framework from KB)
- Design and implementation constraints
- Assumptions and dependencies
- Data model overview: list major entity groups with their key tables
- Session and authentication approach (from session patterns in code)""",
    },
    {
        "key": "functional_requirements",
        "label": "5. Functional Requirements",
        "toon_focus": "CLASSES",
        "min_words": 2000,
        "instructions": """Write EXHAUSTIVE functional requirements grouped by module.
For EACH module found in the KB:

### FR-[MODULE]: [Module Name]
| ID | Requirement | Source Class | DB Tables |
|----|-------------|--------------|-----------|
| FR-[N]-001 | [detailed requirement] | [ClassName] | [table1, table2] |

Requirements must cover:
- Every CRUD operation visible in the controllers
- Every workflow step (approval flows, status transitions)
- Every calculation (LD, penalties, claims if present)
- Every document upload/download operation
- Every report generation
- Every notification/alert
- Every role-based access control rule

Be exhaustive. If you see 50 controllers, write requirements
for all 50. Do not summarise or group multiple requirements
into one line.""",
    },
    {
        "key": "non_functional_requirements",
        "label": "6. Non-Functional Requirements",
        "toon_focus": "TABLES",
        "min_words": 400,
        "instructions": """Write detailed non-functional requirements covering:
- Performance: response times, concurrent users, bulk operation limits
- Security: authentication method, session management, role enforcement,
  encryption (reference actual session patterns from code)
- Scalability: expected data growth (reference actual table counts)
- Availability: uptime, backup requirements
- Data integrity: FK constraints, audit logging requirements
  (reference actual audit log tables found in KB)
- Compliance: regulatory requirements visible in the code
- Migration-specific: data migration approach, zero-downtime requirements,
  rollback strategy""",
    },
    {
        "key": "use_cases",
        "label": "7. Use Cases",
        "toon_focus": "CLASSES",
        "min_words": 1000,
        "instructions": """Write detailed use cases for every major workflow found.
Format each use case as:

### UC-[N]: [Use Case Name]
- **Actor**: [role name]
- **Precondition**: [state before]
- **Main Flow**:
  1. [step referencing actual method names]
  2. [step]
- **Alternative Flows**: [error/rejection paths]
- **Postcondition**: [state after]
- **DB Tables Affected**: [list]

Write at minimum one use case per major controller group found.""",
    },
    {
        "key": "constraints",
        "label": "8. Constraints",
        "toon_focus": "TABLES",
        "min_words": 300,
        "instructions": """Write constraints covering:
- Technology constraints (source stack that must be migrated FROM)
- Target technology requirements
- Database migration constraints (list tables with complex FKs)
- High-risk entities (tables/classes with most dependencies)
- External integration constraints (APIs found in code)
- Data volume constraints (reference actual table counts from KB)
- Timeline and compliance constraints
- Migration risk register: top 10 highest-risk entities with reason""",
    },
    {
        "key": "entity_model",
        "label": "9. Entity Relationship Model",
        "toon_focus": "TABLES",
        "min_words": 0,
        "instructions": "",
    },
]


async def _gen_entity_model(project_id: str) -> dict:
    """Compute ER diagram data deterministically from kb_entities (no LLM).
    Also augments edges by parsing FK statements from the generated OLTP DDL
    so the ER works for legacy schemas where the raw SQL dump has no explicit
    REFERENCES (common in MySQL <5.6 MyISAM and most older PHP apps)."""
    import math
    import re as _re
    from collections import defaultdict as _defaultdict
    from db import data_models as _data_models

    entities = await kb_entities.find(
        {"project_id": project_id, "type": "TABLE"}, {"_id": 0}
    ).to_list(2000)

    nodes = []
    edges = []
    edge_set = set()

    for e in entities:
        parts  = e["name"].split("_")
        domain = parts[0] if len(parts) > 1 else "other"
        node = {
            "id":       e["name"],
            "name":     e["name"],
            "pk":       e.get("pk", ""),
            "domain":   domain,
            "columns": [
                {
                    "name":     c["name"],
                    "type":     c["type"],
                    "is_pk":    c["name"] == e.get("pk", ""),
                    "is_fk":    any(fk["column"] == c["name"]
                                    for fk in e.get("fks", [])),
                    "nullable": True,
                }
                for c in (e.get("columns") or [])
            ],
            "fk_count":  len(e.get("fks", [])),
            "col_count": len(e.get("columns") or []),
        }
        nodes.append(node)
        for fk in (e.get("fks") or []):
            key = f"{e['name']}.{fk['column']}->{fk['ref_table']}"
            if key not in edge_set:
                edge_set.add(key)
                edges.append({
                    "id":          key,
                    "from_table":  e["name"],
                    "from_col":    fk["column"],
                    "to_table":    fk["ref_table"],
                    "type":        "fk",
                    "cardinality": "many-to-one",
                })

    # --- Augmentation 1: parse FK statements from generated OLTP DDL ---
    oltp_art = await _data_models.find_one({"project_id": project_id, "type": "oltp_ddl"}, {"_id": 0})
    ddl = (oltp_art or {}).get("content", "") or ""
    if ddl:
        table_names = {n["id"].lower(): n["id"] for n in nodes}
        # Inline: REFERENCES "other" ("id")  or REFERENCES other(id)
        # Standalone: FOREIGN KEY ("a") REFERENCES "other" ("id")
        # Iterate per CREATE TABLE block so we know the *source* table.
        block_re = _re.compile(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`']?([A-Za-z0-9_\.]+)[\"`']?\s*\((.*?)\)\s*;",
            _re.IGNORECASE | _re.DOTALL,
        )
        fk_re = _re.compile(
            r"FOREIGN\s+KEY\s*\(\s*[\"`']?([A-Za-z0-9_]+)[\"`']?\s*\)\s*"
            r"REFERENCES\s+[\"`']?([A-Za-z0-9_\.]+)[\"`']?\s*\(\s*[\"`']?([A-Za-z0-9_]+)[\"`']?\s*\)",
            _re.IGNORECASE,
        )
        inline_re = _re.compile(
            r"[\"`']?([A-Za-z0-9_]+)[\"`']?\s+[A-Za-z][A-Za-z0-9_()\s,]*?\s+REFERENCES\s+"
            r"[\"`']?([A-Za-z0-9_\.]+)[\"`']?\s*\(\s*[\"`']?([A-Za-z0-9_]+)[\"`']?\s*\)",
            _re.IGNORECASE,
        )
        for m in block_re.finditer(ddl):
            src_table_raw = m.group(1).split(".")[-1]
            body = m.group(2)
            src_table = table_names.get(src_table_raw.lower(), src_table_raw)
            for fm in fk_re.finditer(body):
                from_col, to_table_raw, to_col = fm.group(1), fm.group(2).split(".")[-1], fm.group(3)
                to_table = table_names.get(to_table_raw.lower(), to_table_raw)
                key = f"{src_table}.{from_col}->{to_table}"
                if key in edge_set:
                    continue
                edge_set.add(key)
                edges.append({
                    "id": key, "from_table": src_table, "from_col": from_col,
                    "to_table": to_table, "to_col": to_col, "type": "fk",
                    "cardinality": "many-to-one", "source": "oltp_ddl",
                })
            for fm in inline_re.finditer(body):
                # Skip if the keyword token itself was "FOREIGN" (already matched above)
                if fm.group(1).lower() == "key":
                    continue
                from_col, to_table_raw, to_col = fm.group(1), fm.group(2).split(".")[-1], fm.group(3)
                to_table = table_names.get(to_table_raw.lower(), to_table_raw)
                key = f"{src_table}.{from_col}->{to_table}"
                if key in edge_set:
                    continue
                edge_set.add(key)
                edges.append({
                    "id": key, "from_table": src_table, "from_col": from_col,
                    "to_table": to_table, "to_col": to_col, "type": "fk",
                    "cardinality": "many-to-one", "source": "oltp_ddl",
                })

    # --- Augmentation 2: heuristic inference when neither KB nor OLTP has FKs ---
    # If a table has column "X_id" / "Xid" / "fk_X" and another table named X (or Xs) exists,
    # treat it as a many-to-one relationship. Common in legacy PHP MySQL dumps.
    if not edges:
        name_to_id = {n["id"].lower(): n["id"] for n in nodes}
        # Try both "users" -> "user" and "user" -> "users" matches.
        def _resolve_target(raw):
            cand = raw.lower()
            for c in (cand, cand + "s", cand[:-1] if cand.endswith("s") else cand + "es",
                      "tbl_" + cand, cand.rstrip("s")):
                if c in name_to_id and c != "id":
                    return name_to_id[c]
            return None

        for n in nodes:
            for col in n["columns"]:
                cn = col["name"].lower()
                ref = None
                if cn.endswith("_id") and cn != "id":
                    ref = _resolve_target(cn[:-3])
                elif cn.endswith("id") and len(cn) > 3:
                    ref = _resolve_target(cn[:-2])
                if ref and ref != n["id"]:
                    key = f"{n['id']}.{col['name']}->{ref}"
                    if key in edge_set:
                        continue
                    edge_set.add(key)
                    col["is_fk"] = True
                    n["fk_count"] += 1
                    edges.append({
                        "id": key, "from_table": n["id"], "from_col": col["name"],
                        "to_table": ref, "type": "fk", "cardinality": "many-to-one",
                        "source": "inferred",
                    })

    # Domain-clustered layout
    domain_groups = _defaultdict(list)
    for n in nodes:
        domain_groups[n["domain"]].append(n["id"])

    domain_list = list(domain_groups.keys())
    grid_cols   = max(math.ceil(math.sqrt(len(domain_list))), 1)
    for di, domain in enumerate(domain_list):
        dx      = (di % grid_cols) * 600 + 300
        dy      = (di // grid_cols) * 500 + 300
        members = domain_groups[domain]
        for mi, table_id in enumerate(members):
            angle  = (2 * math.pi * mi) / max(len(members), 1)
            radius = min(40 * len(members), 200)
            for n in nodes:
                if n["id"] == table_id:
                    n["x"]            = dx + radius * math.cos(angle)
                    n["y"]            = dy + radius * math.sin(angle)
                    n["domain_index"] = di
                    break

    er_data = {
        "nodes": nodes,
        "edges": edges,
        "domains": {
            d: {"tables": tbls, "index": i}
            for i, (d, tbls) in enumerate(domain_groups.items())
        },
        "stats": {
            "total_tables":        len(nodes),
            "total_relationships": len(edges),
            "domains":             len(domain_groups),
        },
    }
    return {"content": json.dumps(er_data), "tokens": 0}


def extract_toon_section(toon: str, section_name: str, max_chars: int) -> str:
    """Extract a named section from the TOON output (e.g. 'CLASSES', 'TABLES')."""
    if not toon:
        return ""
    lines = toon.split("\n")
    in_section = False
    result: list[str] = []
    total = 0
    for line in lines:
        if line.startswith(f"# {section_name}"):
            in_section = True
            continue
        if in_section and line.startswith("# "):
            break
        if in_section:
            result.append(line)
            total += len(line)
            if total >= max_chars:
                result.append("...[truncated for context]")
                break
    return "\n".join(result)


async def _get_prompt(project_id: str, key: str) -> str:
    p = await project_prompts.find_one({"project_id": project_id, "key": key}, {"_id": 0})
    if p:
        return p["template"]
    g = await prompts.find_one({"key": key}, {"_id": 0})
    return g["template"] if g else ""


async def _gen_one_section(cfg: dict, proj: dict, full_toon: str, summary: str, convo_text: str, model: str, project_id: str | None = None) -> dict:
    """Generate one SRS section. Returns {'content': ..., 'tokens': int}."""
    # Section 9 is computed deterministically from KB entities — no LLM.
    if cfg["key"] == "entity_model":
        return await _gen_entity_model(project_id or "")

    # Structural skeleton (smaller now since RAG fills in the specifics)
    toon_slice = extract_toon_section(full_toon, cfg["toon_focus"], 4000)
    # Fallback: if the requested focus is missing (e.g. INDIVIDUALS isn't in TOON),
    # use CLASSES + TABLES so the LLM always has structural context to ground on.
    if not toon_slice.strip():
        toon_slice = "\n".join([
            extract_toon_section(full_toon, "CLASSES", 6000),
            extract_toon_section(full_toon, "TABLES", 6000),
        ]).strip() or full_toon[:8000]

    # Semantic RAG: top-15 relevant code/schema chunks for this section
    rag_chunks: list[str] = []
    if project_id:
        query = SECTION_QUERIES.get(cfg["key"], cfg["label"])
        try:
            rag_chunks = await qdrant_search(project_id, query, top_k=15)
        except Exception:
            rag_chunks = []
    rag_context = "\n\n---\n\n".join(rag_chunks) if rag_chunks else ""

    # If no RAG available, keep TOON slice large
    if not rag_context:
        toon_slice = extract_toon_section(full_toon, cfg["toon_focus"], 15000) or toon_slice

    kb_block = (
        f"STRUCTURAL SKELETON (TOON — {cfg['toon_focus']}):\n{toon_slice}"
        + (f"\n\nSEMANTICALLY RELEVANT CODE & SCHEMA:\n{rag_context}" if rag_context else "")
    )

    # Larger sections need a bigger token budget so they aren't cut off mid-document.
    if cfg["min_words"] >= 1500:
        max_tokens = 14000
    elif cfg["min_words"] >= 800:
        max_tokens = 10000
    else:
        max_tokens = 6000

    system_prompt = f"""You are a senior business analyst writing a DETAILED IEEE 830 Software Requirements Specification for a legacy application migration.

PROJECT: {proj.get('name', '')}
SOURCE STACK: {proj.get('source_tech', '')}
TARGET STACK: {proj.get('target_tech', '')}
KB SUMMARY: {summary}
CONVERSATION CONTEXT:
{convo_text}

KNOWLEDGE BASE:
{kb_block}

Write ONLY the "{cfg['label']}" section of the SRS.

{cfg['instructions']}

RULES:
- Use actual class names, table names, method names from the KB above.
- Never write generic placeholders like "[Module Name]" — use real names.
- Minimum {cfg['min_words']} words for this section.
- Format: markdown with sub-headings, bullet lists, tables where appropriate.
- Write as if a developer with zero prior knowledge must implement from scratch.
- Do NOT summarise. Be exhaustive and specific.
- Do NOT refuse, do NOT ask follow-up questions, do NOT output an empty response.
  If the KB seems thin, infer best-practice content from the SOURCE STACK and what classes/tables ARE visible.

Return only the markdown content. No JSON. No preamble."""

    llm_msgs = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Write the {cfg['label']} section now. Be detailed and exhaustive."},
    ]

    last_err: str = ""
    for attempt in range(2):  # 1 retry on empty/parse failure
        try:
            result = await chat_completion(
                messages=llm_msgs,
                model=model,
                temperature=0.2 if attempt == 0 else 0.4,
                max_tokens=max_tokens,
                timeout=240.0,
            )
            content = (result["content"] or "").strip()
            # Some models wrap the response in ```markdown … ``` despite the rules.
            if content.startswith("```"):
                content = content[3:]
                if content[:8].lower().startswith("markdown"):
                    content = content[8:]
                content = content.lstrip("\n")
                if content.endswith("```"):
                    content = content[:-3].rstrip()
            if content.strip():
                return {
                    "content": content,
                    "tokens": result["usage"].get("total_tokens", 0),
                }
            # Empty output — retry once with a more directive nudge.
            last_err = "LLM returned empty content"
            llm_msgs = [
                llm_msgs[0],
                {"role": "user", "content": (
                    f"You returned an empty response. Write the {cfg['label']} section now — "
                    "at least 8 paragraphs, real names from the KB above, no refusals."
                )},
            ]
        except Exception as e:
            last_err = str(e)[:240]
            if attempt == 0:
                continue
    return {"content": f"_[Section generation failed: {last_err}]_", "tokens": 0}


async def _load_srs_context(project_id: str, conversation_id: str | None):
    proj = await projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")

    existing = await srs_documents.find_one({"project_id": project_id}, {"_id": 0})
    if existing and existing.get("frozen"):
        raise HTTPException(400, "SRS is frozen — unfreeze before regenerating")

    toon_doc = await kb_toon.find_one({"project_id": project_id}, {"_id": 0})
    full_toon = (toon_doc or {}).get("toon", "")
    summary = (toon_doc or {}).get("summary", "Knowledge base is empty.")

    q = {"project_id": project_id}
    if conversation_id:
        q["conversation_id"] = conversation_id
    history = await messages.find(q, {"_id": 0}).sort("created_at", 1).to_list(200)
    convo_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history)[-6000:]

    return proj, existing, full_toon, summary, convo_text


async def _persist_srs(project_id: str, existing: dict | None, sections: dict, total_tokens: int, model: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    doc = SRSDocument(
        project_id=project_id,
        sections=sections,
        version=(existing.get("version", 0) + 1) if existing else 1,
    )
    doc_dict = doc.model_dump()
    doc_dict["updated_at"] = now
    await srs_documents.update_one(
        {"project_id": project_id},
        {"$set": doc_dict},
        upsert=True,
    )
    await audit_log.insert_one({
        "action": "srs.generate",
        "project_id": project_id,
        "at": now,
        "details": {
            "model": model,
            "sections": len(sections),
            "version": doc_dict["version"],
            "tokens": total_tokens,
        },
    })
    return doc_dict["version"]


@router.post("/generate")
async def generate_srs(payload: dict):
    """Synchronous JSON generation — runs all 8 sections then returns."""
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")
    conversation_id = payload.get("conversation_id")
    model = payload.get("model") or "deepseek/deepseek-chat"

    proj, existing, full_toon, summary, convo_text = await _load_srs_context(project_id, conversation_id)

    sections: dict[str, str] = {}
    total_tokens = 0
    for cfg in SECTION_CONFIGS:
        r = await _gen_one_section(cfg, proj, full_toon, summary, convo_text, model, project_id=project_id)
        sections[cfg["key"]] = r["content"]
        total_tokens += r["tokens"]
        # incremental save so client can poll GET /srs/{id}
        await srs_documents.update_one(
            {"project_id": project_id},
            {"$set": {
                "project_id": project_id,
                f"sections.{cfg['key']}": r["content"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )

    version = await _persist_srs(project_id, existing, sections, total_tokens, model)
    return {
        "ok": True,
        "sections": sections,
        "version": version,
        "total_tokens": total_tokens,
    }


@router.post("/generate/stream")
async def generate_srs_stream(payload: dict):
    """SSE streaming generation. Emits section_start / section_complete / complete events."""
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")
    conversation_id = payload.get("conversation_id")
    model = payload.get("model") or "deepseek/deepseek-chat"

    proj, existing, full_toon, summary, convo_text = await _load_srs_context(project_id, conversation_id)

    async def event_gen():
        sections: dict[str, str] = {}
        total_tokens = 0
        yield f"data: {json.dumps({'type': 'start', 'total': len(SECTION_CONFIGS), 'project': proj.get('name', '')})}\n\n"

        for i, cfg in enumerate(SECTION_CONFIGS, start=1):
            yield (
                "data: "
                + json.dumps({
                    "type": "section_start",
                    "section": cfg["key"],
                    "label": cfg["label"],
                    "index": i,
                    "total": len(SECTION_CONFIGS),
                })
                + "\n\n"
            )

            # Run the LLM call as a task so we can emit keepalive pings while it runs.
            gen_task = asyncio.create_task(
                _gen_one_section(cfg, proj, full_toon, summary, convo_text, model, project_id=project_id)
            )
            while not gen_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(gen_task), timeout=10.0)
                except asyncio.TimeoutError:
                    # SSE comment ping — keeps proxies / browsers from dropping the connection.
                    yield ": ping\n\n"
                except Exception:
                    break
            r = await gen_task
            sections[cfg["key"]] = r["content"]
            total_tokens += r["tokens"]

            await srs_documents.update_one(
                {"project_id": project_id},
                {"$set": {
                    "project_id": project_id,
                    f"sections.{cfg['key']}": r["content"],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }},
                upsert=True,
            )

            yield (
                "data: "
                + json.dumps({
                    "type": "section_complete",
                    "section": cfg["key"],
                    "label": cfg["label"],
                    "index": i,
                    "total": len(SECTION_CONFIGS),
                    "content": r["content"],
                    "tokens": r["tokens"],
                })
                + "\n\n"
            )
            # let the loop yield to the event loop so the client gets the chunk promptly
            await asyncio.sleep(0)

        version = await _persist_srs(project_id, existing, sections, total_tokens, model)
        yield (
            "data: "
            + json.dumps({
                "type": "complete",
                "version": version,
                "total_tokens": total_tokens,
            })
            + "\n\n"
        )

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/{project_id}")
async def get_srs(project_id: str):
    doc = await srs_documents.find_one({"project_id": project_id}, {"_id": 0})
    if not doc:
        return {
            "project_id": project_id,
            "sections": {k: "" for k in [
                "purpose", "scope", "definitions", "overall_description",
                "functional_requirements", "non_functional_requirements",
                "use_cases", "constraints", "entity_model",
            ]},
            "frozen": False,
            "version": 0,
        }
    return doc


@router.put("/{project_id}/section")
async def update_section(project_id: str, payload: SRSSectionUpdate):
    doc = await srs_documents.find_one({"project_id": project_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "SRS not found — generate first")
    if doc.get("frozen"):
        raise HTTPException(400, "SRS is frozen")
    await srs_documents.update_one(
        {"project_id": project_id},
        {"$set": {
            f"sections.{payload.section}": payload.content,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"ok": True}


@router.post("/freeze")
async def freeze_srs(payload: dict):
    project_id = payload.get("project_id")
    user = payload.get("user", "system")
    srs_doc = await srs_documents.find_one({"project_id": project_id}, {"_id": 0})
    if not srs_doc:
        raise HTTPException(404, "SRS not found")
    now = datetime.now(timezone.utc).isoformat()
    await srs_documents.update_one(
        {"project_id": project_id},
        {"$set": {"frozen": True, "frozen_at": now, "frozen_by": user, "updated_at": now}},
    )
    await projects.update_one(
        {"id": project_id},
        {"$set": {
            "stage_status.Discovery": "frozen",
            "freeze_gates.Discovery": {"at": now, "by": user},
            "updated_at": now,
        }},
    )
    await audit_log.insert_one({
        "action": "srs.freeze",
        "project_id": project_id,
        "at": now,
        "details": {"by": user},
    })

    # ------------------------------------------------------------------
    # Pipeline handoff: persist a StageContext snapshot for downstream stages.
    # Best-effort — never fail the freeze if the snapshot build hiccups.
    # ------------------------------------------------------------------
    try:
        entities = await kb_entities.find({"project_id": project_id}, {"_id": 0}).to_list(100000)
        toon_doc = await kb_toon.find_one({"project_id": project_id}, {"_id": 0})
        proj = await projects.find_one({"id": project_id}, {"_id": 0})

        owl = export_owl(proj or {}, entities, (srs_doc or {}).get("sections", {}))

        domain_map = owl.get("data_model_hints", {}).get("domains", {})
        high_risk = owl.get("data_model_hints", {}).get("high_risk_tables", [])
        boundaries = owl.get("microservice_hints", {}).get("suggested_boundaries", [])
        stats = (toon_doc or {}).get("stats", {})

        tables_only = [e for e in entities if e.get("type") == "TABLE"]
        classes_only = [e for e in entities if e.get("type") == "CLASS"]
        key_tables = sorted(tables_only, key=lambda t: len(t.get("fks") or []), reverse=True)[:80]
        key_classes = sorted(classes_only, key=lambda c: len(c.get("methods") or []), reverse=True)[:60]
        toon_summary = toon_serialise(key_tables + key_classes)[:8000]

        er_nodes = []
        er_edges = []
        edge_set: set[str] = set()
        for e in tables_only:
            parts = e.get("name", "").split("_")
            domain = parts[0] if len(parts) > 1 else "other"
            er_nodes.append({
                "id": e.get("name"),
                "name": e.get("name"),
                "pk": e.get("pk", ""),
                "domain": domain,
                "col_count": len(e.get("columns") or []),
                "fk_count": len(e.get("fks") or []),
            })
            for fk in (e.get("fks") or []):
                key = f"{e.get('name')}.{fk.get('column')}->{fk.get('ref_table')}"
                if key not in edge_set:
                    edge_set.add(key)
                    er_edges.append({
                        "from_table": e.get("name"),
                        "from_col": fk.get("column"),
                        "to_table": fk.get("ref_table"),
                        "type": "fk",
                    })

        ctx = StageContext(
            project_id=project_id,
            stage="Discovery",
            frozen_at=now,
            frozen_by=user,
            version=(srs_doc or {}).get("version", 1),
            outputs={
                "srs_sections": (srs_doc or {}).get("sections", {}),
                "srs_version": (srs_doc or {}).get("version", 1),
                "kb_summary": stats,
                "domain_map": {
                    k: {
                        "tables": v.get("tables", [])[:30],
                        "classes": list(set(v.get("classes", [])))[:15],
                    }
                    for k, v in domain_map.items()
                },
                "high_risk_entities": high_risk[:20],
                "suggested_service_boundaries": boundaries,
                "er_model": {
                    "nodes": er_nodes,
                    "edges": er_edges,
                    "stats": {
                        "total_tables": len(er_nodes),
                        "total_relationships": len(er_edges),
                        "domains": len(domain_map),
                    },
                },
                "owl_export_endpoint": f"/api/kb/{project_id}/owl-export",
                "data_model_hints": owl.get("data_model_hints", {}),
                "microservice_hints": owl.get("microservice_hints", {}),
            },
            toon_summary=toon_summary,
            sources={
                "kb_entities_count": len(entities),
                "kb_stats": stats,
                "srs_version": (srs_doc or {}).get("version", 1),
                "model_used": "multi-model",
                "prompts_used": ["srs.generate", "srs.gap_question"],
            },
        )

        await stage_context_col.update_one(
            {"project_id": project_id, "stage": "Discovery"},
            {"$set": ctx.model_dump()},
            upsert=True,
        )
        await projects.update_one(
            {"id": project_id},
            {"$set": {
                "stage_status.DataModel": "available",
                "updated_at": now,
            }},
        )
    except Exception as exc:
        # Pipeline handoff is best-effort — surface in audit log but don't fail the freeze.
        await audit_log.insert_one({
            "action": "stage_context.build_failed",
            "project_id": project_id,
            "at": now,
            "details": {"stage": "Discovery", "error": str(exc)[:500]},
        })

    return {"ok": True, "frozen_at": now}


@router.post("/unfreeze")
async def unfreeze_srs(payload: dict):
    project_id = payload.get("project_id")
    now = datetime.now(timezone.utc).isoformat()
    await srs_documents.update_one(
        {"project_id": project_id},
        {"$set": {"frozen": False, "updated_at": now}},
    )
    await projects.update_one(
        {"id": project_id},
        {"$set": {"stage_status.Discovery": "active", "updated_at": now}},
    )
    return {"ok": True}


@router.get("/{project_id}/export.pdf")
async def export_pdf(project_id: str):
    doc = await srs_documents.find_one({"project_id": project_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "SRS not found")
    proj = await projects.find_one({"id": project_id}, {"_id": 0})
    pdf_bytes = _render_pdf(proj, doc)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="SRS_{proj.get("name","project")}.pdf"'},
    )


def _render_pdf(project: dict, doc: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
        ListFlowable, ListItem,
    )
    from reportlab.lib.units import cm
    import re as _re

    buf = io.BytesIO()
    pdf = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"SRS - {project.get('name','')}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Title"], fontSize=22, spaceAfter=20, textColor=colors.HexColor("#0A2540"))
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=16, spaceBefore=16, spaceAfter=10, textColor=colors.HexColor("#0A2540"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=13, spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#0A2540"))
    h3 = ParagraphStyle("h3", parent=styles["Heading3"], fontSize=11, spaceBefore=8, spaceAfter=4, textColor=colors.HexColor("#1f2937"))
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10, leading=14, spaceAfter=4)

    def _inline(text: str) -> str:
        """Convert inline markdown to ReportLab mini-HTML."""
        t = text
        # escape angle brackets in code-spans first
        t = _re.sub(r"`([^`]+)`", lambda m: f'<font face="Courier">{m.group(1).replace("<", "&lt;").replace(">", "&gt;")}</font>', t)
        # bold + italic
        t = _re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
        t = _re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", t)
        return t

    def _render_table(md_lines: list[str]) -> Table | None:
        """Convert a contiguous markdown table block (pipe-delimited) to a ReportLab Table."""
        rows: list[list[str]] = []
        for ln in md_lines:
            if _re.match(r"^\|[\s\-:|]+\|$", ln.strip()):
                continue  # separator row
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            rows.append(cells)
        if not rows:
            return None
        # Wrap each cell content in Paragraph for wrapping
        wrapped = [[Paragraph(_inline(c) or "&nbsp;", body) for c in r] for r in rows]
        tbl = Table(wrapped, repeatRows=1, hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A2540")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return tbl

    def _md_to_flowables(md: str) -> list:
        out: list = []
        if not md:
            out.append(Paragraph("<i>(empty)</i>", body))
            return out
        lines = md.split("\n")
        i = 0
        bullet_buf: list[str] = []
        table_buf: list[str] = []

        def _flush_list():
            nonlocal bullet_buf
            if bullet_buf:
                items = [ListItem(Paragraph(_inline(b), body), leftIndent=6) for b in bullet_buf]
                out.append(ListFlowable(items, bulletType="bullet", leftIndent=12, bulletFontSize=8))
                out.append(Spacer(1, 4))
                bullet_buf = []

        def _flush_table():
            nonlocal table_buf
            if table_buf:
                t = _render_table(table_buf)
                if t is not None:
                    out.append(t)
                    out.append(Spacer(1, 6))
                table_buf = []

        while i < len(lines):
            ln = lines[i].rstrip()
            # tables: contiguous block of lines starting with '|'
            if ln.lstrip().startswith("|"):
                _flush_list()
                table_buf.append(ln)
                i += 1
                continue
            else:
                _flush_table()

            if ln.startswith("### "):
                _flush_list()
                out.append(Paragraph(_inline(ln[4:].strip()), h3))
            elif ln.startswith("## "):
                _flush_list()
                out.append(Paragraph(_inline(ln[3:].strip()), h2))
            elif ln.startswith("# "):
                _flush_list()
                out.append(Paragraph(_inline(ln[2:].strip()), h1))
            elif _re.match(r"^\s*[-*]\s+", ln):
                bullet_buf.append(_inline(_re.sub(r"^\s*[-*]\s+", "", ln)))
            elif _re.match(r"^\s*\d+\.\s+", ln):
                bullet_buf.append(_inline(_re.sub(r"^\s*\d+\.\s+", "", ln)))
            elif ln.strip() == "":
                _flush_list()
                out.append(Spacer(1, 4))
            else:
                _flush_list()
                out.append(Paragraph(_inline(ln), body))
            i += 1

        _flush_list()
        _flush_table()
        return out

    elements: list = []
    elements.append(Paragraph("Software Requirements Specification", title_style))
    elements.append(Paragraph(f"<b>Project:</b> {project.get('name','')}", body))
    elements.append(Paragraph(f"<b>Source:</b> {project.get('source_tech','')}  →  <b>Target:</b> {project.get('target_tech','')}", body))
    elements.append(Paragraph(f"<b>Version:</b> {doc.get('version',1)} &nbsp;|&nbsp; <b>Frozen:</b> {doc.get('frozen', False)}", body))
    if doc.get("frozen_at"):
        elements.append(Paragraph(f"<b>Frozen at:</b> {doc.get('frozen_at')} by {doc.get('frozen_by','')}", body))
    elements.append(Spacer(1, 16))

    section_order = [
        ("purpose", "1. Purpose"),
        ("scope", "2. Scope"),
        ("definitions", "3. Definitions, Acronyms & Abbreviations"),
        ("overall_description", "4. Overall Description"),
        ("functional_requirements", "5. Functional Requirements"),
        ("non_functional_requirements", "6. Non-Functional Requirements"),
        ("use_cases", "7. Use Cases"),
        ("constraints", "8. Constraints"),
        ("entity_model", "9. Entity Relationship Model"),
    ]
    sections = doc.get("sections", {})
    for idx, (key, label) in enumerate(section_order):
        if idx > 0:
            elements.append(PageBreak())
        elements.append(Paragraph(label, h1))
        if key == "entity_model":
            # ER section is JSON in storage — render as a text summary in PDF.
            raw = sections.get(key) or ""
            er = {}
            try:
                er = json.loads(raw) if raw else {}
            except Exception:
                er = {}
            stats = (er or {}).get("stats", {})
            domains = list((er or {}).get("domains", {}).keys())
            tables_n = stats.get("total_tables", 0)
            rels_n = stats.get("total_relationships", 0)
            domains_n = stats.get("domains", len(domains))
            summary_line = (
                f"Entity Relationship Model: {tables_n} tables across "
                f"{domains_n} domains with {rels_n} foreign key relationships."
            )
            elements.append(Paragraph(summary_line, body))
            if domains:
                elements.append(Paragraph(
                    f"<b>Key domains:</b> {', '.join(domains[:30])}.", body
                ))
            elements.append(Paragraph(
                "See the interactive ER diagram in LAMA for full visualisation.",
                body,
            ))
            continue
        elements.extend(_md_to_flowables(sections.get(key) or ""))

    pdf.build(elements)
    return buf.getvalue()
