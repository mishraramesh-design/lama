"""Stage 3 — Architecture.

Pipeline-gated by Stage 2 (DataModel) frozen.
Long-running LLM calls run as background jobs (in-memory _JOBS registry, polled by frontend).
"""
import io
import json
import re
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from db import (
    projects,
    audit_log,
    prompts as prompts_col,
    project_prompts,
    arch_documents,
    arch_services,
    kb_entities,
    messages as messages_col,
    conversations,
    stage_context as stage_context_col,
    data_models,
)
from llm import chat_completion
from kb.vector_store import search as qdrant_search
from pipeline import require_stage_context, save_stage_context, get_module_context

logger = logging.getLogger("lama.architecture")
router = APIRouter(prefix="/architecture", tags=["architecture"])

_JOBS: Dict[str, Dict[str, Any]] = {}
_JOB_TTL_SEC = 60 * 60


def _new_job(project_id: str, kind: str) -> str:
    import uuid, time as _t
    jid = uuid.uuid4().hex
    _JOBS[jid] = {
        "id": jid, "project_id": project_id, "kind": kind,
        "status": "queued", "step": "Queued…", "pct": 0,
        "started_at": _t.time(), "ended_at": None,
        "error": None, "result": {},
    }
    now = _t.time()
    for k in [k for k, v in _JOBS.items() if v.get("ended_at") and now - v["ended_at"] > _JOB_TTL_SEC]:
        _JOBS.pop(k, None)
    return jid


def _job_update(jid, **kw):
    if jid in _JOBS:
        _JOBS[jid].update(kw)


def _job_finish(jid, status, **kw):
    import time as _t
    if jid in _JOBS:
        _JOBS[jid]["status"] = status
        _JOBS[jid]["ended_at"] = _t.time()
        _JOBS[jid].update(kw)


async def _get_prompt(project_id: str, key: str) -> str:
    p = await project_prompts.find_one({"project_id": project_id, "key": key}, {"_id": 0})
    if p:
        return p["template"]
    g = await prompts_col.find_one({"key": key}, {"_id": 0})
    return g["template"] if g else ""


def _safe_format(template: str, **vars) -> str:
    return template.format(**{k: (str(v) if v is not None else "") for k, v in vars.items()})


async def _strip_md_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t[3:]
        for tag in ("json", "yaml", "markdown", "md"):
            if t[: len(tag)].lower() == tag:
                t = t[len(tag):]
                break
        t = t.lstrip("\n")
        if t.endswith("```"):
            t = t[:-3].rstrip()
    return t


async def _save_arch_doc(project_id: str, type_: str, content: str, model: str, tracability: dict) -> dict:
    existing = await arch_documents.find_one({"project_id": project_id, "type": type_}, {"_id": 0})
    version = ((existing or {}).get("version", 0)) + 1
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": (existing or {}).get("id") or __import__("uuid").uuid4().hex,
        "project_id": project_id,
        "type": type_,
        "content": content,
        "version": version,
        "frozen": (existing or {}).get("frozen", False),
        "frozen_at": (existing or {}).get("frozen_at"),
        "generated_by": model,
        "tracability": tracability,
        "created_at": (existing or {}).get("created_at", now),
        "updated_at": now,
    }
    await arch_documents.update_one(
        {"project_id": project_id, "type": type_},
        {"$set": doc},
        upsert=True,
    )
    return doc


# -----------------------------------------------------------
# A. recommend (job)
# -----------------------------------------------------------
async def _run_recommend_job(jid: str, project_id: str, model: str, override_message: str = ""):
    try:
        _job_update(jid, status="running", step="Loading DataModel context…", pct=5)
        dm_ctx = await require_stage_context(project_id, "DataModel", "Architecture")
        proj = await projects.find_one({"id": project_id}, {"_id": 0})
        oltp_ddl = (dm_ctx.get("outputs", {}) or {}).get("oltp_ddl", "")[:8000]
        srs_sections = (dm_ctx.get("outputs", {}) or {}).get("srs_sections") or {}
        if not srs_sections:
            disc = await stage_context_col.find_one({"project_id": project_id, "stage": "Discovery"}, {"_id": 0})
            srs_sections = ((disc or {}).get("outputs", {}) or {}).get("srs_sections", {})
        srs_summary = (srs_sections.get("scope", "") + "\n" + srs_sections.get("functional_requirements", ""))[:6000]
        boundaries = (dm_ctx.get("outputs", {}) or {}).get("service_boundaries", []) or []
        table_count = (dm_ctx.get("outputs", {}) or {}).get("oltp_table_count", 0) or 0
        srs_nfr = (srs_sections.get("non_functional_requirements", "") or "").lower()

        score = 0
        if table_count > 100: score += 2
        if table_count > 300: score += 2
        if len(boundaries) > 6: score += 2
        if "concurrent" in srs_nfr: score += 1
        if "10000" in srs_nfr or "high load" in srs_nfr: score += 2

        module_ctx = await get_module_context(project_id)
        complexity_signals = (
            f"Tables: {table_count} | Boundaries detected: {len(boundaries)} | "
            f"Complexity score: {score}/9"
        )

        _job_update(jid, step="Searching knowledge base…", pct=15)
        try:
            rag = await qdrant_search(project_id, "system complexity workflows approval roles concurrent users scalability", top_k=10)
        except Exception:
            rag = []
        rag_context = "\n\n---\n\n".join(rag)[:6000]

        _job_update(jid, step="Building prompt…", pct=22)
        template = await _get_prompt(project_id, "arch.recommend")
        if not template:
            _job_finish(jid, "error", error="arch.recommend prompt missing.")
            return

        system_prompt = _safe_format(
            template,
            project_name=proj.get("name", ""),
            source_tech=proj.get("source_tech", ""),
            backend_lang="nodejs",
            srs_summary=srs_summary,
            oltp_summary=oltp_ddl,
            module_context=module_ctx or "(no module inventory imported)",
            complexity_signals=complexity_signals,
            rag_context=rag_context,
        )
        user_msg = override_message or "Recommend the architecture and decompose into services. Return JSON only."

        _job_update(jid, step="Calling LLM (60-90s typical)…", pct=30)
        gen_task = asyncio.create_task(
            chat_completion(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}],
                model=model, temperature=0.2, max_tokens=8000, timeout=240.0,
            )
        )
        import time as _t
        started = _t.time()
        while not gen_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(gen_task), timeout=3.0)
            except asyncio.TimeoutError:
                el = int(_t.time() - started)
                _job_update(jid, step=f"LLM analysing architecture ({el}s elapsed)…",
                            pct=min(85, 30 + int(55 * (1 - 1 / (1 + el / 25)))))
            except Exception:
                break
        try:
            r = await gen_task
        except Exception as e:
            _job_finish(jid, "error", error=f"LLM failed: {e}")
            return

        raw = await _strip_md_fence(r.get("content", ""))
        try:
            parsed = json.loads(raw)
        except Exception:
            try:
                parsed = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
            except Exception as e:
                _job_finish(jid, "error", error=f"LLM returned non-JSON: {e}")
                return

        _job_update(jid, step="Saving service map…", pct=92)
        # Save service_map artifact
        tracability = {
            "datamodel_version": dm_ctx.get("version"),
            "oltp_table_count": table_count,
            "complexity_score": score,
            "model": model,
            "prompt_key": "arch.recommend",
        }
        art = await _save_arch_doc(project_id, "service_map", json.dumps(parsed, indent=2), model, tracability)

        # Replace existing service definitions
        await arch_services.delete_many({"project_id": project_id})
        services = parsed.get("services", [])
        now = datetime.now(timezone.utc).isoformat()
        svc_docs = []
        for s in services:
            svc_docs.append({
                "id": __import__("uuid").uuid4().hex,
                "project_id": project_id,
                "name": s.get("name", "service"),
                "display_name": s.get("display_name", s.get("name", "")),
                "pattern": parsed.get("recommended_pattern", "microservice"),
                "backend_lang": s.get("backend_lang", "nodejs"),
                "frontend": False,
                "tables": s.get("tables", []) or [],
                "api_endpoints": s.get("api_endpoints", []) or [],
                "dependencies": s.get("dependencies", []) or [],
                "events_published": s.get("events_published", []) or [],
                "events_consumed": s.get("events_consumed", []) or [],
                "status": "pending",
                "codegen_status": "pending",
                "source_module": "",
                "responsibility": s.get("responsibility", ""),
                "estimated_loc": s.get("estimated_loc", 0),
                "created_at": now,
                "updated_at": now,
            })
        # Add frontend as a service
        fe = parsed.get("frontend_service") or {}
        svc_docs.append({
            "id": __import__("uuid").uuid4().hex,
            "project_id": project_id,
            "name": fe.get("name", "frontend"),
            "display_name": "React Frontend",
            "pattern": "frontend",
            "backend_lang": "react",
            "frontend": True,
            "tables": [],
            "api_endpoints": [],
            "dependencies": fe.get("api_consumers", []) or [],
            "events_published": [], "events_consumed": [],
            "status": "pending", "codegen_status": "pending",
            "source_module": "", "responsibility": "User interface",
            "estimated_loc": 0,
            "created_at": now, "updated_at": now,
        })
        if svc_docs:
            await arch_services.insert_many([{**d} for d in svc_docs])

        await audit_log.insert_one({
            "action": "architecture.recommend",
            "project_id": project_id,
            "at": now,
            "details": {"pattern": parsed.get("recommended_pattern"), "service_count": len(services)},
        })

        _job_finish(jid, "complete", step="Done", pct=100,
                    result={"arch_doc_id": art["id"], "version": art["version"],
                            "pattern": parsed.get("recommended_pattern"),
                            "service_count": len(services), "complexity_score": score})
    except HTTPException as he:
        _job_finish(jid, "error", error=he.detail)
    except Exception as e:
        _job_finish(jid, "error", error=str(e))


@router.post("/jobs/start/recommend")
async def start_recommend(payload: dict):
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")
    await require_stage_context(project_id, "DataModel", "Architecture")
    model = payload.get("model") or "deepseek/deepseek-chat"
    msg = payload.get("message", "")
    jid = _new_job(project_id, "recommend")
    asyncio.create_task(_run_recommend_job(jid, project_id, model, msg))
    return {"job_id": jid, "status": "queued"}


# -----------------------------------------------------------
# B. approve service map
# -----------------------------------------------------------
@router.post("/approve")
async def approve_service_map(payload: dict):
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")
    approved = bool(payload.get("approved", True))
    overrides = payload.get("overrides") or []
    sm = await arch_documents.find_one({"project_id": project_id, "type": "service_map"}, {"_id": 0})
    if not sm:
        raise HTTPException(404, "Service map not found — run /jobs/start/recommend first.")

    for o in overrides:
        name = o.get("service_name")
        if not name:
            continue
        upd = {}
        if "backend_lang" in o:
            upd["backend_lang"] = o["backend_lang"]
        if "pattern" in o:
            upd["pattern"] = o["pattern"]
        if upd:
            await arch_services.update_one({"project_id": project_id, "name": name}, {"$set": upd})

    if approved:
        now = datetime.now(timezone.utc).isoformat()
        await arch_documents.update_one(
            {"project_id": project_id, "type": "service_map"},
            {"$set": {"frozen": True, "frozen_at": now, "updated_at": now}},
        )
        await audit_log.insert_one({
            "action": "architecture.approve",
            "project_id": project_id,
            "at": now,
            "details": {"overrides": overrides},
        })

    return {"ok": True, "approved": approved}


# -----------------------------------------------------------
# C. HLD generation (job)
# -----------------------------------------------------------
HLD_SECTIONS = [
    ("executive_summary", "Executive Summary", "Concise overview of the proposed architecture, key drivers, and outcomes.", 200),
    ("system_context", "System Context Diagram", "Use a Mermaid C4Context diagram showing the system, users, and external integrations.", 250),
    ("service_decomposition", "Service Decomposition", "One subsection per service: responsibility, owned tables, key endpoints.", 600),
    ("api_gateway", "API Gateway & Routing Strategy", "Describe routing, auth pass-through, rate-limit, observability headers.", 250),
    ("data_flow", "Data Flow Diagrams", "Mermaid sequenceDiagram for the top 3 critical workflows.", 350),
    ("database_arch", "Database Architecture", "Database-per-service vs. shared-DB, schema-by-bounded-context, transactions.", 250),
    ("auth", "Authentication & Authorization", "JWT issuance, session, RBAC, service-to-service auth.", 200),
    ("nfr", "Non-Functional Requirements", "Map SRS NFRs to architecture decisions: latency, throughput, availability.", 250),
    ("deployment", "Deployment Architecture", "Mermaid graph LR diagram: containers, ingress, observability, DB.", 250),
    ("tech_decisions", "Technology Decisions & Justifications", "Why each chosen lang/framework. Trade-offs.", 200),
]


async def _run_hld_job(jid: str, project_id: str, model: str):
    try:
        _job_update(jid, status="running", step="Loading service map…", pct=2)
        dm_ctx = await require_stage_context(project_id, "DataModel", "Architecture")
        proj = await projects.find_one({"id": project_id}, {"_id": 0})
        sm = await arch_documents.find_one({"project_id": project_id, "type": "service_map"}, {"_id": 0})
        if not sm or not sm.get("frozen"):
            _job_finish(jid, "error", error="Service map must be approved (frozen) first.")
            return
        try:
            sm_data = json.loads(sm["content"])
        except Exception:
            sm_data = {}
        services = sm_data.get("services", [])
        services_summary = "\n".join(
            f"- {s.get('name')}: {s.get('responsibility','')} (tables: {len(s.get('tables') or [])})"
            for s in services
        )
        srs_sections = (dm_ctx.get("outputs", {}) or {}).get("srs_sections") or {}
        if not srs_sections:
            disc = await stage_context_col.find_one({"project_id": project_id, "stage": "Discovery"}, {"_id": 0})
            srs_sections = ((disc or {}).get("outputs", {}) or {}).get("srs_sections", {})
        srs_functional = (srs_sections.get("functional_requirements", "") or "")[:5000]
        oltp_summary = ((dm_ctx.get("outputs", {}) or {}).get("oltp_ddl", "") or "")[:4000]

        template = await _get_prompt(project_id, "arch.hld")
        if not template:
            _job_finish(jid, "error", error="arch.hld prompt missing.")
            return

        sections_md: List[Dict[str, str]] = [None] * len(HLD_SECTIONS)
        total = len(HLD_SECTIONS)
        completed = {"n": 0}
        sem = asyncio.Semaphore(4)  # parallel LLM calls

        async def gen_section(i, key, label, instructions, min_words):
            async with sem:
                system_prompt = _safe_format(
                    template,
                    project_name=proj.get("name", ""),
                    recommended_pattern=sm_data.get("recommended_pattern", ""),
                    services_summary=services_summary,
                    srs_functional=srs_functional,
                    oltp_summary=oltp_summary,
                    section_name=label,
                    section_instructions=instructions,
                    min_words=str(min_words),
                )
                try:
                    r = await chat_completion(
                        messages=[{"role": "system", "content": system_prompt},
                                  {"role": "user", "content": f"Write the {label} section now."}],
                        model=model, temperature=0.2, max_tokens=4000, timeout=180.0,
                    )
                    section_md = (r.get("content", "") or "").strip()
                except Exception as e:
                    section_md = f"## {label}\n\n_Generation error: {e}_"
                completed["n"] += 1
                pct = 5 + int((completed["n"] / total) * 90)
                _job_update(jid, step=f"Section {completed['n']}/{total}: {label}", pct=pct)
                sections_md[i] = {"key": key, "label": label, "content": section_md}

        _job_update(jid, step=f"Generating {total} sections in parallel…", pct=5)
        await asyncio.gather(*[
            gen_section(i, k, lab, instr, mw)
            for i, (k, lab, instr, mw) in enumerate(HLD_SECTIONS)
        ])

        # Assemble final HLD
        full = "\n\n".join(f"## {s['label']}\n\n{s['content']}" for s in sections_md)
        tracability = {
            "datamodel_version": dm_ctx.get("version"),
            "service_map_version": sm.get("version"),
            "section_count": total,
            "model": model,
            "prompt_key": "arch.hld",
        }
        art = await _save_arch_doc(project_id, "hld", full, model, tracability)
        await audit_log.insert_one({
            "action": "architecture.generate.hld",
            "project_id": project_id,
            "at": datetime.now(timezone.utc).isoformat(),
            "details": {"version": art["version"], "sections": total},
        })
        _job_finish(jid, "complete", step="Done", pct=100,
                    result={"arch_doc_id": art["id"], "version": art["version"], "sections": total})
    except HTTPException as he:
        _job_finish(jid, "error", error=he.detail)
    except Exception as e:
        _job_finish(jid, "error", error=str(e))


@router.post("/jobs/start/hld")
async def start_hld(payload: dict):
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")
    await require_stage_context(project_id, "DataModel", "Architecture")
    model = payload.get("model") or "deepseek/deepseek-chat"
    jid = _new_job(project_id, "hld")
    asyncio.create_task(_run_hld_job(jid, project_id, model))
    return {"job_id": jid, "status": "queued"}


# -----------------------------------------------------------
# D. LLD generation (job) — one section per service
# -----------------------------------------------------------
async def _run_lld_job(jid: str, project_id: str, model: str):
    try:
        _job_update(jid, status="running", step="Loading services…", pct=2)
        dm_ctx = await require_stage_context(project_id, "DataModel", "Architecture")
        proj = await projects.find_one({"id": project_id}, {"_id": 0})
        services = await arch_services.find({"project_id": project_id, "frontend": False}, {"_id": 0}).to_list(50)
        if not services:
            _job_finish(jid, "error", error="No services. Generate service map first.")
            return
        hld_doc = await arch_documents.find_one({"project_id": project_id, "type": "hld"}, {"_id": 0})
        hld_summary = (hld_doc.get("content", "") if hld_doc else "")[:4000]
        oltp_ddl = (dm_ctx.get("outputs", {}) or {}).get("oltp_ddl", "")
        template = await _get_prompt(project_id, "arch.lld")
        if not template:
            _job_finish(jid, "error", error="arch.lld prompt missing.")
            return

        total = len(services)
        per_service: List[str] = [None] * total
        completed = {"n": 0}
        sem = asyncio.Semaphore(4)

        async def gen_lld(i, svc):
            async with sem:
                relevant_ddl = "\n".join(
                    line for line in oltp_ddl.split("\n")
                    if any(t in line for t in (svc.get("tables") or []))
                )[:4000]
                sp = _safe_format(
                    template,
                    project_name=proj.get("name", ""),
                    service_name=svc.get("name", ""),
                    service_responsibility=svc.get("responsibility", ""),
                    backend_lang=svc.get("backend_lang", "nodejs"),
                    service_tables=", ".join(svc.get("tables", []) or []),
                    service_endpoints="\n".join(svc.get("api_endpoints", []) or []),
                    service_dependencies=", ".join(svc.get("dependencies", []) or []),
                    hld_summary=hld_summary,
                    relevant_ddl=relevant_ddl or "(no DDL excerpt for this service)",
                )
                try:
                    r = await chat_completion(
                        messages=[{"role": "system", "content": sp},
                                  {"role": "user", "content": f"Write the LLD for {svc['name']} now."}],
                        model=model, temperature=0.2, max_tokens=6000, timeout=200.0,
                    )
                    content = (r.get("content", "") or "").strip()
                except Exception as e:
                    content = f"## {svc['name']}\n\n_Generation error: {e}_"
                completed["n"] += 1
                pct = 5 + int((completed["n"] / total) * 90)
                _job_update(jid, step=f"LLD {completed['n']}/{total}: {svc['name']}", pct=pct)
                per_service[i] = f"# Service: {svc['display_name']} (`{svc['name']}`)\n\n{content}"

        _job_update(jid, step=f"Generating LLD for {total} services in parallel…", pct=5)
        await asyncio.gather(*[gen_lld(i, svc) for i, svc in enumerate(services)])

        full = "\n\n---\n\n".join(per_service)
        tracability = {"service_count": total, "model": model, "prompt_key": "arch.lld"}
        art = await _save_arch_doc(project_id, "lld", full, model, tracability)

        # Extract OpenAPI YAML blocks into api_contracts
        yaml_blocks = re.findall(r"```yaml\n(.*?)```", full, re.DOTALL)
        if yaml_blocks:
            await _save_arch_doc(project_id, "api_contracts", "\n---\n".join(yaml_blocks), model,
                                 {"merged_from_lld": True, "block_count": len(yaml_blocks)})

        _job_finish(jid, "complete", step="Done", pct=100,
                    result={"arch_doc_id": art["id"], "version": art["version"], "services": total,
                            "api_contracts_extracted": len(yaml_blocks)})
    except HTTPException as he:
        _job_finish(jid, "error", error=he.detail)
    except Exception as e:
        _job_finish(jid, "error", error=str(e))


@router.post("/jobs/start/lld")
async def start_lld(payload: dict):
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")
    await require_stage_context(project_id, "DataModel", "Architecture")
    model = payload.get("model") or "deepseek/deepseek-chat"
    jid = _new_job(project_id, "lld")
    asyncio.create_task(_run_lld_job(jid, project_id, model))
    return {"job_id": jid, "status": "queued"}


# -----------------------------------------------------------
# E. Sequence diagrams (job)
# -----------------------------------------------------------
async def _run_seq_job(jid: str, project_id: str, model: str):
    try:
        _job_update(jid, status="running", step="Loading use cases…", pct=2)
        dm_ctx = await require_stage_context(project_id, "DataModel", "Architecture")
        proj = await projects.find_one({"id": project_id}, {"_id": 0})
        srs_sections = (dm_ctx.get("outputs", {}) or {}).get("srs_sections") or {}
        if not srs_sections:
            disc = await stage_context_col.find_one({"project_id": project_id, "stage": "Discovery"}, {"_id": 0})
            srs_sections = ((disc or {}).get("outputs", {}) or {}).get("srs_sections", {})
        use_cases_text = srs_sections.get("use_cases", "") or ""
        # Cheap split: lines starting with "## " or "UC-"
        cases = [c.strip() for c in re.split(r"\n(?=##\s|UC-)", use_cases_text) if c.strip()][:5]
        if not cases:
            cases = ["Top workflow"]
        services = await arch_services.find({"project_id": project_id, "frontend": False}, {"_id": 0}).to_list(50)
        services_list = ", ".join(s["name"] for s in services)
        endpoints = "\n".join(f"{s['name']}: {', '.join((s.get('api_endpoints') or [])[:5])}" for s in services)

        template = await _get_prompt(project_id, "arch.sequence")
        if not template:
            _job_finish(jid, "error", error="arch.sequence prompt missing.")
            return

        diagrams: List[Dict[str, str]] = [None] * len(cases)
        total = len(cases)
        completed = {"n": 0}
        sem = asyncio.Semaphore(4)

        async def gen_seq(i, uc):
            async with sem:
                label = uc.split("\n")[0][:80].lstrip("# ").strip() or f"Workflow {i+1}"
                sp = _safe_format(
                    template,
                    project_name=proj.get("name", ""),
                    use_case_name=label,
                    use_case_content=uc[:1500],
                    services_list=services_list,
                    relevant_endpoints=endpoints[:2000],
                )
                try:
                    r = await chat_completion(
                        messages=[{"role": "system", "content": sp},
                                  {"role": "user", "content": "Generate the mermaid sequenceDiagram now."}],
                        model=model, temperature=0.2, max_tokens=2500, timeout=120.0,
                    )
                    content = (r.get("content", "") or "").strip()
                except Exception as e:
                    content = f"```mermaid\nsequenceDiagram\n  Note over System: error: {e}\n```"
                completed["n"] += 1
                pct = 5 + int((completed["n"] / total) * 90)
                _job_update(jid, step=f"Diagram {completed['n']}/{total}: {label}", pct=pct)
                diagrams[i] = {"use_case": label, "mermaid": content}

        _job_update(jid, step=f"Generating {total} diagrams in parallel…", pct=5)
        await asyncio.gather(*[gen_seq(i, uc) for i, uc in enumerate(cases)])

        body = "\n\n".join(f"## {d['use_case']}\n\n{d['mermaid']}" for d in diagrams)
        tracability = {"use_case_count": total, "model": model, "prompt_key": "arch.sequence"}
        art = await _save_arch_doc(project_id, "sequence_diagrams", body, model, tracability)
        _job_finish(jid, "complete", step="Done", pct=100,
                    result={"arch_doc_id": art["id"], "version": art["version"], "diagrams": total})
    except HTTPException as he:
        _job_finish(jid, "error", error=he.detail)
    except Exception as e:
        _job_finish(jid, "error", error=str(e))


@router.post("/jobs/start/sequence")
async def start_seq(payload: dict):
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")
    await require_stage_context(project_id, "DataModel", "Architecture")
    model = payload.get("model") or "deepseek/deepseek-chat"
    jid = _new_job(project_id, "sequence")
    asyncio.create_task(_run_seq_job(jid, project_id, model))
    return {"job_id": jid, "status": "queued"}


# -----------------------------------------------------------
# Job poll
# -----------------------------------------------------------
@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    j = _JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    return {"id": j["id"], "status": j["status"], "step": j.get("step", ""),
            "pct": j.get("pct", 0), "error": j.get("error"),
            "result": j.get("result", {}), "kind": j.get("kind")}


# -----------------------------------------------------------
# F. Chat
# -----------------------------------------------------------
@router.post("/chat")
async def arch_chat(payload: dict):
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")
    message = (payload.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message required")
    model = payload.get("model") or "deepseek/deepseek-chat"
    target = payload.get("target_artifact") or "all"
    conv_id = payload.get("conversation_id")

    await require_stage_context(project_id, "DataModel", "Architecture")
    proj = await projects.find_one({"id": project_id}, {"_id": 0})

    arts = await arch_documents.find({"project_id": project_id}, {"_id": 0}).to_list(20)
    arch_context_parts = []
    for a in arts:
        if target == "all" or target == a["type"]:
            arch_context_parts.append(f"## {a['type']}\n\n{a.get('content','')[:4000]}")
    arch_context = "\n\n".join(arch_context_parts)[:10000]

    try:
        rag = await qdrant_search(project_id, message, top_k=5)
    except Exception:
        rag = []
    rag_context = "\n\n---\n\n".join(rag)[:4000]

    template = await _get_prompt(project_id, "arch.chat")
    sp = _safe_format(template, project_name=proj.get("name", ""),
                      arch_context=arch_context, rag_context=rag_context, message=message)

    if not conv_id:
        conv_id = __import__("uuid").uuid4().hex
        await conversations.insert_one({"id": conv_id, "project_id": project_id, "stage": "Architecture",
                                        "created_at": datetime.now(timezone.utc).isoformat()})
    await messages_col.insert_one({
        "id": __import__("uuid").uuid4().hex, "conversation_id": conv_id, "project_id": project_id,
        "role": "user", "content": message, "created_at": datetime.now(timezone.utc).isoformat(),
    })

    try:
        r = await chat_completion(
            messages=[{"role": "system", "content": sp}, {"role": "user", "content": message}],
            model=model, temperature=0.2, max_tokens=4000, timeout=120.0,
        )
    except Exception as e:
        raise HTTPException(502, f"LLM failed: {e}")
    content = r.get("content", "") or ""

    changes = []
    for tag, ctype in (("HLD_CHANGE", "hld_section_update"),
                       ("ARCH_CHANGE", "service_modify"),
                       ("LLD_CHANGE", "lld_service_update")):
        for m in re.finditer(rf"\[{tag}:([^\]]+)\]\s*(.*?)\s*\[/{tag}\]", content, re.DOTALL):
            changes.append({"type": ctype, "target": m.group(1).strip(), "new_content": m.group(2).strip()})
    for m in re.finditer(r"\[SERVICE_ADD\]\s*(.*?)\s*\[/SERVICE_ADD\]", content, re.DOTALL):
        changes.append({"type": "service_add", "target": "", "new_content": m.group(1).strip()})
    for m in re.finditer(r"\[SERVICE_REMOVE:([^\]]+)\]", content):
        changes.append({"type": "service_remove", "target": m.group(1).strip(), "new_content": ""})

    msg_id = __import__("uuid").uuid4().hex
    await messages_col.insert_one({
        "id": msg_id, "conversation_id": conv_id, "project_id": project_id,
        "role": "assistant", "content": content, "model": model,
        "tokens": r.get("usage", {}).get("total_tokens", 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"conversation_id": conv_id, "message_id": msg_id, "content": content, "changes": changes}


# -----------------------------------------------------------
# G. Apply changes
# -----------------------------------------------------------
@router.post("/{project_id}/apply-changes")
async def apply_changes(project_id: str, payload: dict):
    changes = payload.get("changes") or []
    updated = []
    now = datetime.now(timezone.utc).isoformat()
    for ch in changes:
        ctype = ch.get("type")
        target = ch.get("target", "")
        body = ch.get("new_content", "")
        if ctype == "hld_section_update":
            doc = await arch_documents.find_one({"project_id": project_id, "type": "hld"}, {"_id": 0})
            if doc and not doc.get("frozen"):
                # naive section replace by ## header line
                content = doc["content"]
                pattern = re.compile(rf"(## {re.escape(target)}.*?)(?=\n## |\Z)", re.DOTALL | re.IGNORECASE)
                if pattern.search(content):
                    new = pattern.sub(f"## {target}\n\n{body}\n", content)
                else:
                    new = content + f"\n\n## {target}\n\n{body}\n"
                await arch_documents.update_one(
                    {"project_id": project_id, "type": "hld"},
                    {"$set": {"content": new, "version": doc.get("version", 1) + 1, "updated_at": now}},
                )
                updated.append({"type": "hld", "section": target})
        elif ctype == "service_modify":
            try:
                svc = json.loads(body)
                await arch_services.update_one(
                    {"project_id": project_id, "name": target},
                    {"$set": {**svc, "updated_at": now}},
                )
                updated.append({"type": "service_modify", "service": target})
            except Exception:
                pass
        elif ctype == "service_add":
            try:
                svc = json.loads(body)
                svc.update({"id": __import__("uuid").uuid4().hex, "project_id": project_id,
                            "status": "pending", "codegen_status": "pending",
                            "created_at": now, "updated_at": now, "frontend": False})
                await arch_services.insert_one(svc)
                updated.append({"type": "service_add", "service": svc.get("name")})
            except Exception:
                pass
        elif ctype == "service_remove":
            await arch_services.delete_one({"project_id": project_id, "name": target})
            updated.append({"type": "service_remove", "service": target})
    await audit_log.insert_one({
        "action": "architecture.apply_changes",
        "project_id": project_id, "at": now,
        "details": {"updated": updated, "request_id": payload.get("conversation_message_id")},
    })
    return {"ok": True, "updated": updated}


# -----------------------------------------------------------
# H/I/J/K — CRUD + freeze + reset
# -----------------------------------------------------------
@router.get("/{project_id}/artifacts")
async def list_artifacts(project_id: str):
    arts = await arch_documents.find({"project_id": project_id}, {"_id": 0}).sort("updated_at", -1).to_list(100)
    services = await arch_services.find({"project_id": project_id}, {"_id": 0}).to_list(100)
    return {"artifacts": arts, "services": services}


@router.get("/{project_id}/artifact/{artifact_id}")
async def get_arch_artifact(project_id: str, artifact_id: str):
    a = await arch_documents.find_one({"project_id": project_id, "id": artifact_id}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Artifact not found")
    return a


@router.put("/{project_id}/artifact/{artifact_id}")
async def update_arch_artifact(project_id: str, artifact_id: str, payload: dict):
    doc = await arch_documents.find_one({"project_id": project_id, "id": artifact_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Artifact not found")
    if doc.get("frozen"):
        raise HTTPException(400, "Artifact is frozen")
    new_content = payload.get("content", "")
    now = datetime.now(timezone.utc).isoformat()
    await arch_documents.update_one(
        {"project_id": project_id, "id": artifact_id},
        {"$set": {"content": new_content, "version": doc.get("version", 1) + 1, "updated_at": now}},
    )
    return {"ok": True}


@router.get("/{project_id}/artifact/{artifact_id}/download")
async def download_arch(project_id: str, artifact_id: str):
    a = await arch_documents.find_one({"project_id": project_id, "id": artifact_id}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Artifact not found")
    ext = "yaml" if a["type"] == "api_contracts" else ("json" if a["type"] == "service_map" else "md")
    fn = f"{a['type']}.{ext}"
    return StreamingResponse(io.BytesIO((a.get("content", "") or "").encode("utf-8")),
                             media_type="text/plain",
                             headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@router.post("/{project_id}/artifact/{artifact_id}/freeze")
async def freeze_arch_artifact(project_id: str, artifact_id: str):
    a = await arch_documents.find_one({"project_id": project_id, "id": artifact_id}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Artifact not found")
    now = datetime.now(timezone.utc).isoformat()
    await arch_documents.update_one(
        {"project_id": project_id, "id": artifact_id},
        {"$set": {"frozen": True, "frozen_at": now, "updated_at": now}},
    )
    await audit_log.insert_one({
        "action": "architecture.artifact.freeze",
        "project_id": project_id, "at": now,
        "details": {"type": a["type"], "version": a.get("version", 1)},
    })

    # If the canonical core artifacts are frozen, freeze the whole stage
    sm = await arch_documents.find_one({"project_id": project_id, "type": "service_map"}, {"_id": 0})
    hld = await arch_documents.find_one({"project_id": project_id, "type": "hld"}, {"_id": 0})
    lld = await arch_documents.find_one({"project_id": project_id, "type": "lld"}, {"_id": 0})
    if sm and sm.get("frozen") and hld and hld.get("frozen") and lld and lld.get("frozen"):
        seq = await arch_documents.find_one({"project_id": project_id, "type": "sequence_diagrams"}, {"_id": 0})
        api = await arch_documents.find_one({"project_id": project_id, "type": "api_contracts"}, {"_id": 0})
        services = await arch_services.find({"project_id": project_id}, {"_id": 0}).to_list(100)
        try:
            sm_data = json.loads(sm["content"])
        except Exception:
            sm_data = {}
        outputs = {
            "pattern": sm_data.get("recommended_pattern"),
            "services": services,
            "hld_content": hld.get("content", ""),
            "lld_content": lld.get("content", ""),
            "api_contracts": (api or {}).get("content", ""),
            "sequence_diagrams": (seq or {}).get("content", ""),
            "service_count": len(services),
            "frontend_service": sm_data.get("frontend_service", {}),
            "backend_lang": (services[0]["backend_lang"] if services else "nodejs"),
            "event_bus": sm_data.get("event_bus", False),
        }
        dm_ctx = await stage_context_col.find_one({"project_id": project_id, "stage": "DataModel"}, {"_id": 0})
        sources = {
            "datamodel_version": (dm_ctx or {}).get("version"),
            "model_used": a.get("generated_by", ""),
            "prompts_used": ["arch.recommend", "arch.hld", "arch.lld", "arch.sequence"],
        }
        await save_stage_context(project_id, "Architecture", outputs, sources, frozen_by="system")
        await projects.update_one(
            {"id": project_id},
            {"$set": {"stage_status.Architecture": "frozen",
                      "stage_status.CodeGen": "available",
                      "updated_at": now}},
        )
    return {"ok": True}


@router.post("/{project_id}/reset")
async def reset_arch(project_id: str):
    deleted = {
        "arch_documents": (await arch_documents.delete_many({"project_id": project_id})).deleted_count,
        "arch_services": (await arch_services.delete_many({"project_id": project_id})).deleted_count,
    }
    await stage_context_col.delete_one({"project_id": project_id, "stage": "Architecture"})
    now = datetime.now(timezone.utc).isoformat()
    await projects.update_one(
        {"id": project_id},
        {"$set": {"stage_status.Architecture": "available",
                  "stage_status.CodeGen": "locked",
                  "stage_status.Living": "locked",
                  "updated_at": now}},
    )
    await audit_log.insert_one({
        "action": "architecture.reset",
        "project_id": project_id, "at": now, "details": deleted,
    })
    return {"ok": True, "deleted": deleted}
