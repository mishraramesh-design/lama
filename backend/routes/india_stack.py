"""India-Stack integration routes (architecture-stage palette + codegen + living dashboard)."""
from __future__ import annotations
from datetime import datetime, timezone
import logging
import uuid

from fastapi import APIRouter, HTTPException

from db import (
    projects,
    india_stack_selections,
    india_stack_usage,
    codegen_files,
    audit_log,
    arch_services,
)
from india_stack.catalog import CATALOG, by_id
from india_stack.code_generator import generate_for_project

logger = logging.getLogger("lama.india_stack")
router = APIRouter(prefix="/india-stack", tags=["india-stack"])


@router.get("/catalog")
async def get_catalog():
    """Return the static catalog the Architecture page renders as draggable palette cards."""
    return {"components": CATALOG}


@router.get("/{project_id}/selections")
async def get_selections(project_id: str):
    """Current India-Stack selections for the project (drag-and-drop state)."""
    doc = await india_stack_selections.find_one({"project_id": project_id}, {"_id": 0})
    return doc or {"project_id": project_id, "selections": [], "updated_at": None}


@router.put("/{project_id}/selections")
async def save_selections(project_id: str, payload: dict):
    """Replace the entire selection set for a project.

    Body: { "selections": [
        {"component_id": "aadhaar_ekyc",
         "attach_to": "user-service" | "new",
         "mode": "mock" | "sandbox",
         "sandbox_provider": "Setu" | …,
         "env": {"AADHAAR_CLIENT_ID": "…"}}, …
    ]}
    """
    proj = await projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")

    selections = payload.get("selections") or []
    # Validate each entry references a known component.
    for sel in selections:
        if not by_id(sel.get("component_id", "")):
            raise HTTPException(400, f"Unknown component_id: {sel.get('component_id')}")
        sel.setdefault("mode", "mock")
        sel.setdefault("env", {})
        sel.setdefault("attach_to", "new")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "project_id": project_id,
        "selections": selections,
        "updated_at": now,
    }
    await india_stack_selections.update_one(
        {"project_id": project_id},
        {"$set": doc},
        upsert=True,
    )
    await audit_log.insert_one({
        "action": "india_stack.selections.update",
        "project_id": project_id,
        "at": now,
        "details": {"count": len(selections), "components": [s["component_id"] for s in selections]},
    })
    return {"ok": True, **doc}


@router.post("/{project_id}/generate")
async def generate_code(project_id: str):
    """Emit code files for the currently-selected components into the codegen_files collection.

    Stage 4 (CodeGen) picks them up automatically because they share the same collection.
    """
    proj = await projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")
    sel_doc = await india_stack_selections.find_one({"project_id": project_id}, {"_id": 0})
    if not sel_doc or not sel_doc.get("selections"):
        raise HTTPException(400, "No India-Stack components selected — drag at least one onto a service first.")

    files = generate_for_project(sel_doc["selections"])
    now = datetime.now(timezone.utc).isoformat()
    written = []
    for f in files:
        fid = uuid.uuid4().hex
        doc = {
            "id": fid,
            "project_id": project_id,
            "service_name": f.get("service_name", "india-stack"),
            "file_path": f["path"],
            "content": f["content"],
            "kind": f.get("kind", "backend"),
            "source": "india_stack",
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
        # Upsert by (project_id, file_path) so re-generation overwrites cleanly.
        existing = await codegen_files.find_one(
            {"project_id": project_id, "file_path": f["path"]}, {"_id": 0}
        )
        if existing:
            doc["id"] = existing["id"]
            doc["version"] = (existing.get("version") or 0) + 1
            doc["created_at"] = existing.get("created_at", now)
            await codegen_files.update_one(
                {"project_id": project_id, "file_path": f["path"]},
                {"$set": doc},
            )
        else:
            await codegen_files.insert_one(doc)
        written.append({"path": doc["file_path"], "version": doc["version"], "kind": doc["kind"]})

    await audit_log.insert_one({
        "action": "india_stack.generate",
        "project_id": project_id,
        "at": now,
        "details": {"files": len(written), "components": [s["component_id"] for s in sel_doc["selections"]]},
    })
    return {"ok": True, "files": written, "count": len(written)}


# ─── Living-stage dashboard ─────────────────────────────────────────────────
@router.get("/{project_id}/living")
async def living_dashboard(project_id: str):
    """Usage + compliance + drift summary for the Living stage."""
    sel_doc = await india_stack_selections.find_one({"project_id": project_id}, {"_id": 0})
    selections = (sel_doc or {}).get("selections") or []
    by_component: dict[str, dict] = {}

    # Usage counts (last 7 / 30 days)
    usage_rows = await india_stack_usage.find({"project_id": project_id}, {"_id": 0}).to_list(10000)
    for u in usage_rows:
        comp = u.get("component_id", "")
        by_component.setdefault(comp, {"total": 0, "errors": 0})
        by_component[comp]["total"] += 1
        if u.get("status") != "ok":
            by_component[comp]["errors"] += 1

    out_rows = []
    for sel in selections:
        cat = by_id(sel["component_id"])
        if not cat:
            continue
        usage = by_component.get(sel["component_id"], {"total": 0, "errors": 0})

        # Compliance score (rough): mode + env-vars-filled + low error rate
        env_filled = sum(1 for v in sel.get("env", {}).values() if v)
        env_total = len(cat["env_vars"]) or 1
        error_rate = (usage["errors"] / usage["total"]) if usage["total"] > 0 else 0
        score = 100
        if sel.get("mode") == "mock":
            score -= 30
        score -= int((env_total - env_filled) / env_total * 30)
        score -= int(error_rate * 40)
        score = max(0, min(100, score))

        # Drift placeholder — would compare provider OpenAPI hashes in real impl
        drift = "ok" if usage["errors"] == 0 else "warning"

        out_rows.append({
            "component_id": sel["component_id"],
            "name": cat["name"],
            "category": cat["category"],
            "mode": sel.get("mode", "mock"),
            "sandbox_provider": sel.get("sandbox_provider", ""),
            "attach_to": sel.get("attach_to", "new"),
            "usage_total": usage["total"],
            "usage_errors": usage["errors"],
            "error_rate": round(error_rate * 100, 1),
            "compliance_score": score,
            "drift_status": drift,
            "env_filled": env_filled,
            "env_total": env_total,
        })

    return {
        "project_id": project_id,
        "rows": out_rows,
        "totals": {
            "components": len(out_rows),
            "calls": sum(r["usage_total"] for r in out_rows),
            "errors": sum(r["usage_errors"] for r in out_rows),
            "avg_compliance": round(
                sum(r["compliance_score"] for r in out_rows) / max(len(out_rows), 1), 1
            ),
        },
    }


@router.post("/{project_id}/usage")
async def record_usage(project_id: str, payload: dict):
    """Append a usage record. Generated backend code calls this from its middleware."""
    component_id = payload.get("component_id")
    if not component_id or not by_id(component_id):
        raise HTTPException(400, "Valid component_id required")
    doc = {
        "id": uuid.uuid4().hex,
        "project_id": project_id,
        "component_id": component_id,
        "endpoint": payload.get("endpoint", ""),
        "status": payload.get("status", "ok"),
        "duration_ms": payload.get("duration_ms", 0),
        "user_id": payload.get("user_id", ""),
        "error": payload.get("error", ""),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    await india_stack_usage.insert_one(doc)
    return {"ok": True}


# ─── Architecture-stage helper: list existing services to use as drop targets ─
@router.get("/{project_id}/services")
async def list_services_for_dragdrop(project_id: str):
    """Return existing arch_services (drop targets) plus 'new service' synthetic target."""
    svcs = await arch_services.find({"project_id": project_id}, {"_id": 0}).to_list(200)
    out = [{"name": s.get("name", ""), "display_name": s.get("display_name", s.get("name", ""))} for s in svcs]
    out.insert(0, {"name": "new", "display_name": "+ New microservice"})
    return {"services": out}
