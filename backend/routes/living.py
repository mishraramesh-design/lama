"""Stage 5 — Living System.

Generates:
  - Selenium acceptance tests (test.selenium)
  - JMeter performance plans (test.jmeter)
  - Drift reports (drift.detector)
  - SRS diff reports (diff.srs)

All long LLM calls use the in-memory job polling pattern (no SSE),
identical to architecture.py / codegen.py to bypass K8s 60s ingress timeouts.
"""
import asyncio
import io
import logging
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from db import (
    projects,
    srs_documents,
    living_artifacts,
    living_runs,
    arch_documents,
    arch_services,
    project_prompts,
    prompts as prompts_col,
)
from llm import fabric_call
from pipeline import require_stage_context, save_stage_context


async def get_prompt_for_project(project_id: str, key: str) -> str:
    p = await project_prompts.find_one({"project_id": project_id, "key": key}, {"_id": 0})
    if p:
        return p.get("template", "")
    g = await prompts_col.find_one({"key": key}, {"_id": 0})
    return (g or {}).get("template", "")

logger = logging.getLogger("lama.living")

router = APIRouter(prefix="/living", tags=["living"])

# ─── In-memory job registry (same pattern as architecture/codegen) ─────
_JOBS: Dict[str, Dict[str, Any]] = {}


def _new_job(project_id: str, kind: str) -> str:
    jid = uuid.uuid4().hex
    _JOBS[jid] = {
        "id": jid, "kind": kind, "project_id": project_id,
        "status": "queued", "step": "queued", "pct": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None, "error": "", "result": None,
    }
    return jid


def _job_update(jid: str, **kwargs):
    if jid in _JOBS:
        _JOBS[jid].update(kwargs)


def _job_complete(jid: str, result: Dict[str, Any]):
    _job_update(jid, status="complete", step="Done", pct=100, result=result,
                completed_at=datetime.now(timezone.utc).isoformat())


def _job_error(jid: str, err: str):
    _job_update(jid, status="error", error=err,
                completed_at=datetime.now(timezone.utc).isoformat())


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


# ─── Helpers to assemble inputs ────────────────────────────────────────
async def _assemble_context(project_id: str) -> Dict[str, str]:
    proj = await projects.find_one({"id": project_id}, {"_id": 0}) or {}
    srs = await srs_documents.find_one({"project_id": project_id}, {"_id": 0}) or {}
    services = await arch_services.find({"project_id": project_id}, {"_id": 0}).to_list(200)
    sections = srs.get("sections", {}) or {}
    routes_text = "\n".join(
        f"{(s.get('name') or '')}: {ep}" for s in services for ep in (s.get("api_endpoints") or [])
    ) or "(no service map yet)"
    use_cases = (sections.get("use_cases") or "").strip() or "(no use cases yet)"
    nfr = (sections.get("non_functional_requirements") or "").strip() or "(no NFR section)"
    return {
        "project_name": proj.get("name", ""),
        "target_tech": proj.get("target_tech", "FastAPI + React + PostgreSQL"),
        "use_cases": use_cases[:8000],
        "routes": routes_text[:6000],
        "endpoints": routes_text[:6000],
        "srs_functional": (sections.get("functional_requirements") or "")[:10000],
        "nfr_summary": nfr[:4000],
        "base_url": proj.get("deploy_base_url", "http://localhost:8001"),
    }


def _split_files(raw: str) -> List[Dict[str, str]]:
    """Split LLM output on `=== FILE: <path> ===` markers."""
    out: List[Dict[str, str]] = []
    parts = raw.split("=== FILE:")
    for p in parts[1:]:
        nl = p.find("\n")
        if nl < 0:
            continue
        header = p[:nl].strip()
        body = p[nl + 1:]
        path = header.rstrip("=").strip()
        if not path:
            continue
        # Strip the trailing ===' that may close the marker
        body = body.split("=== FILE:")[0].strip()
        if body.endswith("==="):
            body = body[:-3].rstrip()
        out.append({"path": path, "content": body})
    if not out:
        out.append({"path": "output.txt", "content": raw})
    return out


async def _save_artifact(project_id: str, kind: str, files: List[Dict[str, str]], meta: Dict[str, Any]):
    now = datetime.now(timezone.utc).isoformat()
    existing = await living_artifacts.find_one({"project_id": project_id, "kind": kind}, {"_id": 0})
    if existing:
        await living_artifacts.update_one(
            {"id": existing["id"]},
            {"$set": {
                "files": files, "meta": meta,
                "version": existing.get("version", 1) + 1,
                "updated_at": now, "frozen": False,
            }},
        )
        return existing["id"]
    art_id = uuid.uuid4().hex
    await living_artifacts.insert_one({
        "id": art_id, "project_id": project_id, "kind": kind,
        "files": files, "meta": meta,
        "version": 1, "frozen": False,
        "created_at": now, "updated_at": now,
    })
    return art_id


# ─── Job runners ──────────────────────────────────────────────────────
async def _run_generic(jid: str, project_id: str, agent_key: str, kind: str, model: str = ""):
    try:
        _job_update(jid, status="running", step="Loading context…", pct=8)
        ctx = await _assemble_context(project_id)
        _job_update(jid, step="Rendering prompt…", pct=18)
        template = await get_prompt_for_project(project_id, agent_key)
        if not template:
            raise RuntimeError(f"Prompt {agent_key} not found")
        try:
            system_prompt = template.format(**ctx)
        except KeyError as e:
            raise RuntimeError(f"Missing template variable {e}; available: {list(ctx.keys())}")

        _job_update(jid, step=f"Calling {agent_key} LLM…", pct=35)
        r = await fabric_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Generate {kind} now."},
            ],
            agent_key=agent_key, project_id=project_id,
            model_override=model, max_tokens=8000, temperature=0.2, timeout=200.0,
        )
        raw = (r.get("content") or "").strip()

        _job_update(jid, step="Persisting artifact…", pct=88)
        files = _split_files(raw) if kind in {"selenium", "jmeter"} else [
            {"path": f"{kind}.md", "content": raw}
        ]
        art_id = await _save_artifact(project_id, kind, files, {"model": r.get("model"), "agent_key": agent_key})

        _job_complete(jid, {"artifact_id": art_id, "kind": kind,
                            "files_count": len(files), "model": r.get("model")})
    except Exception as e:
        logger.exception(f"living job {kind} failed: {e}")
        _job_error(jid, str(e)[:500])


@router.post("/jobs/start/selenium")
async def start_selenium(payload: dict):
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")
    await require_stage_context(project_id, "CodeGen", "Living")
    jid = _new_job(project_id, "selenium")
    asyncio.create_task(_run_generic(jid, project_id, "test.selenium", "selenium",
                                     payload.get("model", "")))
    return {"job_id": jid, "status": "queued"}


@router.post("/jobs/start/jmeter")
async def start_jmeter(payload: dict):
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")
    await require_stage_context(project_id, "CodeGen", "Living")
    jid = _new_job(project_id, "jmeter")
    asyncio.create_task(_run_generic(jid, project_id, "test.jmeter", "jmeter",
                                     payload.get("model", "")))
    return {"job_id": jid, "status": "queued"}


@router.post("/jobs/start/drift")
async def start_drift(payload: dict):
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")
    await require_stage_context(project_id, "CodeGen", "Living")
    live_signals = payload.get("live_signals", "") or "(no live signals attached)"
    jid = _new_job(project_id, "drift")

    async def _run():
        try:
            _job_update(jid, status="running", step="Loading SRS…", pct=15)
            ctx = await _assemble_context(project_id)
            ctx["live_signals"] = live_signals[:8000]
            tpl = await get_prompt_for_project(project_id, "drift.detector")
            if not tpl:
                raise RuntimeError("drift.detector prompt missing")
            sys_p = tpl.format(**ctx)
            _job_update(jid, step="Detecting drift…", pct=45)
            r = await fabric_call(
                messages=[{"role": "system", "content": sys_p},
                          {"role": "user", "content": "Produce the drift report."}],
                agent_key="drift.detector", project_id=project_id,
                max_tokens=5000, temperature=0.1, timeout=180.0,
            )
            content = (r.get("content") or "").strip()
            art_id = await _save_artifact(project_id, "drift", [{"path": "drift_report.md", "content": content}],
                                          {"model": r.get("model"), "live_signals_chars": len(live_signals)})
            _job_complete(jid, {"artifact_id": art_id, "kind": "drift"})
        except Exception as e:
            _job_error(jid, str(e)[:500])

    asyncio.create_task(_run())
    return {"job_id": jid, "status": "queued"}


@router.post("/jobs/start/srs-diff")
async def start_srs_diff(payload: dict):
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")
    await require_stage_context(project_id, "CodeGen", "Living")
    srs_a = (payload.get("srs_a") or "").strip()
    srs_b = (payload.get("srs_b") or "").strip()
    if not srs_a or not srs_b:
        raise HTTPException(400, "srs_a and srs_b required (raw markdown)")
    jid = _new_job(project_id, "srs-diff")

    async def _run():
        try:
            _job_update(jid, status="running", step="Diffing…", pct=30)
            tpl = await get_prompt_for_project(project_id, "diff.srs")
            sys_p = (tpl or "").format(srs_a=srs_a[:10000], srs_b=srs_b[:10000])
            r = await fabric_call(
                messages=[{"role": "system", "content": sys_p},
                          {"role": "user", "content": "Produce the diff."}],
                agent_key="diff.srs", project_id=project_id,
                max_tokens=4000, temperature=0.1, timeout=120.0,
            )
            content = (r.get("content") or "").strip()
            art_id = await _save_artifact(project_id, "srs_diff", [{"path": "srs_diff.md", "content": content}],
                                          {"model": r.get("model")})
            _job_complete(jid, {"artifact_id": art_id, "kind": "srs_diff"})
        except Exception as e:
            _job_error(jid, str(e)[:500])

    asyncio.create_task(_run())
    return {"job_id": jid, "status": "queued"}


# ─── CRUD for artifacts ──────────────────────────────────────────────
@router.get("/{project_id}/artifacts")
async def list_artifacts(project_id: str):
    rows = await living_artifacts.find({"project_id": project_id}, {"_id": 0, "files": 0}).to_list(100)
    return {"artifacts": rows, "count": len(rows)}


@router.get("/{project_id}/artifact/{artifact_id}")
async def get_artifact(project_id: str, artifact_id: str):
    a = await living_artifacts.find_one({"id": artifact_id, "project_id": project_id}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Artifact not found")
    return a


@router.put("/{project_id}/artifact/{artifact_id}")
async def update_artifact(project_id: str, artifact_id: str, payload: dict):
    files = payload.get("files")
    if not isinstance(files, list):
        raise HTTPException(400, "files (list) required")
    now = datetime.now(timezone.utc).isoformat()
    r = await living_artifacts.update_one(
        {"id": artifact_id, "project_id": project_id, "frozen": {"$ne": True}},
        {"$set": {"files": files, "updated_at": now}, "$inc": {"version": 1}},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Artifact not found or frozen")
    return {"ok": True}


@router.post("/{project_id}/artifact/{artifact_id}/freeze")
async def freeze_artifact(project_id: str, artifact_id: str):
    now = datetime.now(timezone.utc).isoformat()
    r = await living_artifacts.update_one(
        {"id": artifact_id, "project_id": project_id},
        {"$set": {"frozen": True, "frozen_at": now, "updated_at": now}},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Artifact not found")
    return {"ok": True}


@router.post("/{project_id}/artifact/{artifact_id}/download")
@router.get("/{project_id}/artifact/{artifact_id}/download")
async def download_artifact(project_id: str, artifact_id: str):
    a = await living_artifacts.find_one({"id": artifact_id, "project_id": project_id}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Artifact not found")
    files = a.get("files", [])
    if len(files) == 1:
        f = files[0]
        body = (f.get("content") or "").encode("utf-8")
        return StreamingResponse(io.BytesIO(body), media_type="text/plain",
                                 headers={"Content-Disposition": f"attachment; filename={f['path'].split('/')[-1]}"})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.writestr(f.get("path", "file.txt"), f.get("content", ""))
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f"attachment; filename={a['kind']}_{project_id[:8]}.zip"})


@router.post("/{project_id}/freeze")
async def freeze_stage(project_id: str):
    now = datetime.now(timezone.utc).isoformat()
    await projects.update_one(
        {"id": project_id},
        {"$set": {"stage_status.Living": "frozen", "updated_at": now}},
    )
    return {"ok": True}


@router.post("/{project_id}/reset")
async def reset_stage(project_id: str):
    await living_artifacts.delete_many({"project_id": project_id})
    await living_runs.delete_many({"project_id": project_id})
    now = datetime.now(timezone.utc).isoformat()
    await projects.update_one(
        {"id": project_id},
        {"$set": {"stage_status.Living": "available", "updated_at": now}},
    )
    return {"ok": True}
