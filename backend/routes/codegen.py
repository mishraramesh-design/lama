"""Stage 4 — Code Generation. Pipeline-gated by Architecture frozen."""
import io
import json
import re
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from db import (
    projects, audit_log, prompts as prompts_col, project_prompts,
    arch_documents, arch_services, codegen_files, codegen_runs,
    messages as messages_col, conversations, stage_context as stage_context_col,
    data_models,
)
from llm import chat_completion
from kb.vector_store import search as qdrant_search
from pipeline import require_stage_context, save_stage_context
from codegen.zip_builder import build_zip
from codegen.file_templates import get_file_instruction, get_frontend_instruction

logger = logging.getLogger("lama.codegen")
router = APIRouter(prefix="/codegen", tags=["codegen"])

_JOBS: Dict[str, Dict[str, Any]] = {}
_JOB_TTL_SEC = 60 * 60


def _new_job(project_id: str, kind: str) -> str:
    import uuid, time as _t
    jid = uuid.uuid4().hex
    _JOBS[jid] = {"id": jid, "project_id": project_id, "kind": kind,
                  "status": "queued", "step": "Queued…", "pct": 0,
                  "started_at": _t.time(), "ended_at": None,
                  "error": None, "result": {}, "log": []}
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


def _job_log(jid, line):
    if jid in _JOBS:
        _JOBS[jid]["log"].append(line)
        _JOBS[jid]["log"] = _JOBS[jid]["log"][-200:]


async def _get_prompt(project_id: str, key: str) -> str:
    p = await project_prompts.find_one({"project_id": project_id, "key": key}, {"_id": 0})
    if p:
        return p["template"]
    g = await prompts_col.find_one({"key": key}, {"_id": 0})
    return g["template"] if g else ""


def _safe_format(template: str, **vars) -> str:
    return template.format(**{k: (str(v) if v is not None else "") for k, v in vars.items()})


def _strip_md_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t[3:]
        for tag in ("javascript", "typescript", "python", "java", "go", "yaml", "json", "sql", "markdown", "md", "tsx", "jsx", "js", "ts", "py", "dockerfile", "Dockerfile"):
            if t[:len(tag)].lower() == tag.lower():
                t = t[len(tag):]
                break
        t = t.lstrip("\n")
        if t.endswith("```"):
            t = t[:-3].rstrip()
    return t


# Service file plan (kept short to control token budget)
def _backend_files_plan(svc: dict) -> List[dict]:
    lang = svc.get("backend_lang", "nodejs")
    name = svc["name"]
    base = f"services/{name}"
    plan = [
        {"path": f"{base}/Dockerfile", "type": "dockerfile", "language": "dockerfile"},
        {"path": f"{base}/.env.example", "type": "config", "language": "ini"},
        {"path": f"{base}/README.md", "type": "docs", "language": "markdown"},
    ]
    if lang == "nodejs":
        plan += [
            {"path": f"{base}/package.json", "type": "config", "language": "json"},
            {"path": f"{base}/src/index.js", "type": "route", "language": "javascript"},
            {"path": f"{base}/src/models/{name}-model.js", "type": "model", "language": "javascript"},
            {"path": f"{base}/src/services/{name}-service.js", "type": "service", "language": "javascript"},
            {"path": f"{base}/src/middleware/auth.js", "type": "middleware", "language": "javascript"},
            {"path": f"{base}/tests/{name}.test.js", "type": "test", "language": "javascript"},
        ]
    elif lang == "python":
        plan += [
            {"path": f"{base}/requirements.txt", "type": "config", "language": "text"},
            {"path": f"{base}/app/main.py", "type": "route", "language": "python"},
            {"path": f"{base}/app/models.py", "type": "model", "language": "python"},
            {"path": f"{base}/app/services.py", "type": "service", "language": "python"},
            {"path": f"{base}/app/auth.py", "type": "middleware", "language": "python"},
            {"path": f"{base}/tests/test_{name}.py", "type": "test", "language": "python"},
        ]
    elif lang == "java":
        pkg = name.replace("-", "")
        plan += [
            {"path": f"{base}/pom.xml", "type": "config", "language": "xml"},
            {"path": f"{base}/src/main/java/com/lama/{pkg}/Application.java", "type": "route", "language": "java"},
            {"path": f"{base}/src/main/java/com/lama/{pkg}/Controller.java", "type": "route", "language": "java"},
            {"path": f"{base}/src/main/java/com/lama/{pkg}/ServiceImpl.java", "type": "service", "language": "java"},
        ]
    elif lang == "go":
        plan += [
            {"path": f"{base}/go.mod", "type": "config", "language": "text"},
            {"path": f"{base}/main.go", "type": "route", "language": "go"},
            {"path": f"{base}/internal/handler.go", "type": "route", "language": "go"},
            {"path": f"{base}/internal/service.go", "type": "service", "language": "go"},
        ]
    return plan


def _frontend_files_plan(svc: dict) -> List[dict]:
    base = "frontend"
    return [
        {"path": f"{base}/Dockerfile", "type": "dockerfile", "language": "dockerfile", "ctype": "scaffold"},
        {"path": f"{base}/package.json", "type": "config", "language": "json", "ctype": "scaffold"},
        {"path": f"{base}/src/api/client.ts", "type": "service", "language": "typescript", "ctype": "api_client"},
        {"path": f"{base}/src/store/auth.ts", "type": "service", "language": "typescript", "ctype": "store"},
        {"path": f"{base}/src/routes.tsx", "type": "config", "language": "typescript", "ctype": "route_config"},
        {"path": f"{base}/src/pages/Dashboard.tsx", "type": "route", "language": "typescript", "ctype": "page"},
        {"path": f"{base}/README.md", "type": "docs", "language": "markdown", "ctype": "scaffold"},
    ]


async def _gen_one_file(project_id: str, svc: dict, file_def: dict, model: str, run_doc: dict) -> str:
    """Generate one file via LLM. Returns content (may include error inline)."""
    proj = await projects.find_one({"id": project_id}, {"_id": 0})
    arch_ctx = await stage_context_col.find_one({"project_id": project_id, "stage": "Architecture"}, {"_id": 0})
    lld_full = ((arch_ctx or {}).get("outputs", {}) or {}).get("lld_content", "")
    # Crude per-service slice
    svc_lld = ""
    m = re.search(rf"# Service:[^\n]*`{re.escape(svc['name'])}`(.*?)(?=\n# Service:|\Z)", lld_full, re.DOTALL)
    if m:
        svc_lld = m.group(1)[:6000]
    else:
        svc_lld = lld_full[:4000]

    if svc.get("frontend"):
        template = await _get_prompt(project_id, "codegen.frontend")
        component_type = file_def.get("ctype", "page")
        api_arts = await arch_documents.find_one({"project_id": project_id, "type": "api_contracts"}, {"_id": 0})
        api_summary = (api_arts.get("content", "") if api_arts else "")[:3000]
        sp = _safe_format(
            template,
            project_name=proj.get("name", ""),
            component_type=component_type,
            file_path=file_def["path"],
            api_summary=api_summary,
            relevant_use_cases=svc_lld[:2000],
            component_instructions=get_frontend_instruction(component_type),
        )
    else:
        template = await _get_prompt(project_id, "codegen.service")
        dm_ctx = await stage_context_col.find_one({"project_id": project_id, "stage": "DataModel"}, {"_id": 0})
        oltp_ddl = ((dm_ctx or {}).get("outputs", {}) or {}).get("oltp_ddl", "")
        relevant_ddl = "\n".join(
            ln for ln in oltp_ddl.split("\n")
            if any(t in ln for t in (svc.get("tables") or []))
        )[:3000]
        sp = _safe_format(
            template,
            project_name=proj.get("name", ""),
            service_name=svc.get("name", ""),
            service_responsibility=svc.get("responsibility", ""),
            backend_lang=svc.get("backend_lang", "nodejs"),
            service_lld=svc_lld,
            service_ddl=relevant_ddl or "(no DDL excerpt)",
            service_endpoints="\n".join(svc.get("api_endpoints", []) or []),
            service_dependencies=", ".join(svc.get("dependencies", []) or []),
            file_path=file_def["path"],
            file_type=file_def["type"],
            file_type_instructions=get_file_instruction(file_def["type"], svc.get("backend_lang", "nodejs")),
        )

    try:
        r = await chat_completion(
            messages=[{"role": "system", "content": sp},
                      {"role": "user", "content": f"Generate {file_def['path']} now."}],
            model=model, temperature=0.2, max_tokens=4500, timeout=180.0,
        )
        return _strip_md_fence(r.get("content", "")) or f"// LAMA: empty content for {file_def['path']}"
    except Exception as e:
        return f"// LAMA generation error for {file_def['path']}: {e}\n"


async def _save_codegen_file(run_id: str, project_id: str, svc: dict, file_def: dict, content: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    existing = await codegen_files.find_one({"project_id": project_id, "file_path": file_def["path"]}, {"_id": 0})
    doc = {
        "id": (existing or {}).get("id") or __import__("uuid").uuid4().hex,
        "project_id": project_id,
        "service_id": svc.get("id", ""),
        "service_name": svc.get("name", ""),
        "file_path": file_def["path"],
        "content": content,
        "language": file_def.get("language", "text"),
        "file_type": file_def.get("type", "other"),
        "version": ((existing or {}).get("version", 0)) + 1,
        "edited": False,
        "created_at": (existing or {}).get("created_at", now),
        "updated_at": now,
    }
    await codegen_files.update_one(
        {"project_id": project_id, "file_path": file_def["path"]},
        {"$set": doc}, upsert=True,
    )
    return doc


# -----------------------------------------------------------
# A. generate all (job)
# -----------------------------------------------------------
async def _run_codegen_job(jid: str, project_id: str, model: str, only_service: str = None):
    try:
        _job_update(jid, status="running", step="Loading architecture context…", pct=1)
        arch_ctx = await require_stage_context(project_id, "Architecture", "CodeGen")
        proj = await projects.find_one({"id": project_id}, {"_id": 0})
        services_q = {"project_id": project_id}
        if only_service:
            services_q["name"] = only_service
        services = await arch_services.find(services_q, {"_id": 0}).to_list(100)
        if not services:
            _job_finish(jid, "error", error="No services to generate.")
            return

        # Plan all files
        all_files: List[tuple] = []  # (svc, filedef)
        for svc in services:
            plan = _frontend_files_plan(svc) if svc.get("frontend") else _backend_files_plan(svc)
            for f in plan:
                all_files.append((svc, f))

        # Plus root-level files
        root_files = [
            ({"name": "_root", "frontend": False, "backend_lang": "any",
              "responsibility": "project root", "tables": [], "api_endpoints": [],
              "dependencies": [], "id": ""},
             {"path": "docker-compose.yml", "type": "compose", "language": "yaml"}),
            ({"name": "_root", "frontend": False, "backend_lang": "any",
              "responsibility": "project root", "tables": [], "api_endpoints": [],
              "dependencies": [], "id": ""},
             {"path": ".github/workflows/ci.yml", "type": "ci", "language": "yaml"}),
            ({"name": "_root", "frontend": False, "backend_lang": "any",
              "responsibility": "project root", "tables": [], "api_endpoints": [],
              "dependencies": [], "id": ""},
             {"path": "README.md", "type": "docs", "language": "markdown"}),
        ]
        if not only_service:
            all_files.extend(root_files)

        run = {
            "id": jid, "project_id": project_id, "status": "running",
            "services_total": len(services), "services_done": 0,
            "files_total": len(all_files), "files_done": 0,
            "errors": [], "github_commit": "",
            "started_at": datetime.now(timezone.utc).isoformat(), "completed_at": None,
        }
        await codegen_runs.update_one({"id": jid}, {"$set": run}, upsert=True)

        # Clear old files for affected services
        if only_service:
            await codegen_files.delete_many({"project_id": project_id, "service_name": only_service})

        files_done = 0
        last_svc = None
        services_done = 0
        for svc, file_def in all_files:
            files_done += 1
            if svc["name"] != last_svc:
                if last_svc is not None and last_svc != "_root":
                    services_done += 1
                last_svc = svc["name"]
            base_pct = 2 + int((files_done / max(1, len(all_files))) * 95)
            _job_update(jid, step=f"[{files_done}/{len(all_files)}] {file_def['path']}", pct=base_pct)
            _job_log(jid, file_def["path"])
            content = await _gen_one_file(project_id, svc, file_def, model, run)
            await _save_codegen_file(jid, project_id, svc, file_def, content)
            await codegen_runs.update_one({"id": jid}, {"$set": {"files_done": files_done, "services_done": services_done}})

        await codegen_runs.update_one(
            {"id": jid},
            {"$set": {"status": "complete", "completed_at": datetime.now(timezone.utc).isoformat(),
                      "services_done": len(services), "files_done": files_done}},
        )
        await audit_log.insert_one({
            "action": "codegen.generate",
            "project_id": project_id,
            "at": datetime.now(timezone.utc).isoformat(),
            "details": {"run_id": jid, "files": files_done, "services": len(services)},
        })
        _job_finish(jid, "complete", step="Done", pct=100,
                    result={"run_id": jid, "files": files_done, "services": len(services)})
    except HTTPException as he:
        _job_finish(jid, "error", error=he.detail)
    except Exception as e:
        _job_finish(jid, "error", error=str(e))


@router.post("/jobs/start/generate")
async def start_codegen(payload: dict):
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")
    await require_stage_context(project_id, "Architecture", "CodeGen")
    model = payload.get("model") or "deepseek/deepseek-chat"
    only = payload.get("service_name")
    jid = _new_job(project_id, "codegen")
    asyncio.create_task(_run_codegen_job(jid, project_id, model, only_service=only))
    return {"job_id": jid, "status": "queued"}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    j = _JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    return {"id": j["id"], "status": j["status"], "step": j.get("step", ""),
            "pct": j.get("pct", 0), "error": j.get("error"),
            "result": j.get("result", {}), "kind": j.get("kind"),
            "log": j.get("log", [])[-20:]}


# -----------------------------------------------------------
# C/D/E. Files CRUD
# -----------------------------------------------------------
@router.get("/{project_id}/files")
async def list_files(project_id: str):
    docs = await codegen_files.find({"project_id": project_id},
                                    {"_id": 0, "content": 0}).sort("file_path", 1).to_list(2000)
    by_svc: Dict[str, List[dict]] = {}
    for d in docs:
        by_svc.setdefault(d.get("service_name", "_root"), []).append({
            "id": d["id"], "path": d["file_path"], "language": d.get("language", "text"),
            "file_type": d.get("file_type", "other"), "version": d.get("version", 1),
            "edited": d.get("edited", False),
        })
    services = [{"name": k, "files": v} for k, v in by_svc.items()]
    return {"services": services, "total_files": len(docs)}


@router.get("/{project_id}/file/{file_id}")
async def get_file(project_id: str, file_id: str):
    d = await codegen_files.find_one({"project_id": project_id, "id": file_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "File not found")
    return d


@router.put("/{project_id}/file/{file_id}")
async def update_file(project_id: str, file_id: str, payload: dict):
    d = await codegen_files.find_one({"project_id": project_id, "id": file_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "File not found")
    new_content = payload.get("content", "")
    now = datetime.now(timezone.utc).isoformat()
    await codegen_files.update_one(
        {"project_id": project_id, "id": file_id},
        {"$set": {"content": new_content, "version": d.get("version", 1) + 1,
                  "edited": True, "updated_at": now}},
    )
    await audit_log.insert_one({
        "action": "codegen.file.update",
        "project_id": project_id, "at": now,
        "details": {"file_path": d["file_path"], "version": d.get("version", 1) + 1},
    })
    return {"ok": True}


# -----------------------------------------------------------
# F. download zip
# -----------------------------------------------------------
@router.post("/{project_id}/download-zip")
async def download_zip(project_id: str):
    proj = await projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")
    files = await codegen_files.find({"project_id": project_id}, {"_id": 0}).to_list(5000)
    if not files:
        raise HTTPException(400, "No files to package. Generate code first.")
    blob = build_zip(proj.get("name", "lama"), files)
    fn = (proj.get("name", "lama") or "lama").lower().replace(" ", "_") + ".zip"
    return StreamingResponse(io.BytesIO(blob), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{fn}"'})


# -----------------------------------------------------------
# G. push to GitHub (job)
# -----------------------------------------------------------
async def _run_github_push_job(jid: str, project_id: str):
    try:
        from db import github_configs
        cfg = await github_configs.find_one({"project_id": project_id}, {"_id": 0})
        if not cfg or not cfg.get("token") or not cfg.get("repo_url"):
            _job_finish(jid, "error", error="GitHub not configured for this project. Configure in /settings.")
            return
        from github import Github
        from urllib.parse import urlparse

        parsed = urlparse(cfg["repo_url"])
        repo_full = parsed.path.strip("/").replace(".git", "")
        gh = Github(cfg["token"])
        repo = gh.get_repo(repo_full)
        branch = cfg.get("branch", "main")

        files = await codegen_files.find({"project_id": project_id}, {"_id": 0}).to_list(5000)
        if not files:
            _job_finish(jid, "error", error="No files to push.")
            return

        last_sha = ""
        for i, f in enumerate(files):
            base_pct = 2 + int((i / len(files)) * 95)
            _job_update(jid, step=f"[{i+1}/{len(files)}] {f['file_path']}", pct=base_pct)
            try:
                existing = repo.get_contents(f["file_path"], ref=branch)
                r = repo.update_file(f["file_path"], f"LAMA codegen: {f['file_path']}",
                                     f["content"], existing.sha, branch=branch)
            except Exception:
                r = repo.create_file(f["file_path"], f"LAMA codegen: {f['file_path']}",
                                     f["content"], branch=branch)
            try:
                last_sha = r["commit"].sha if r and r.get("commit") else last_sha
            except Exception:
                last_sha = last_sha
        await codegen_runs.update_one({"id": jid}, {"$set": {"github_commit": last_sha}})
        _job_finish(jid, "complete", step="Done", pct=100,
                    result={"commit_sha": last_sha, "repo_url": cfg["repo_url"], "files": len(files)})
    except Exception as e:
        _job_finish(jid, "error", error=str(e))


@router.post("/jobs/start/github-push")
async def start_github_push(payload: dict):
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")
    jid = _new_job(project_id, "github_push")
    asyncio.create_task(_run_github_push_job(jid, project_id))
    return {"job_id": jid, "status": "queued"}


# -----------------------------------------------------------
# H. chat
# -----------------------------------------------------------
@router.post("/chat")
async def codegen_chat(payload: dict):
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")
    message = (payload.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message required")
    model = payload.get("model") or "deepseek/deepseek-chat"
    file_id = payload.get("file_id")
    service_name = payload.get("service_name")
    conv_id = payload.get("conversation_id")

    await require_stage_context(project_id, "Architecture", "CodeGen")
    proj = await projects.find_one({"id": project_id}, {"_id": 0})

    file_doc = None
    related_context = ""
    file_path = ""
    if file_id:
        file_doc = await codegen_files.find_one({"project_id": project_id, "id": file_id}, {"_id": 0})
        if file_doc:
            file_path = file_doc["file_path"]
    if service_name:
        peers = await codegen_files.find({"project_id": project_id, "service_name": service_name},
                                         {"_id": 0}).to_list(20)
        related_context = "\n\n".join(f"--- {p['file_path']} ---\n{p['content'][:1500]}" for p in peers[:5])

    try:
        rag = await qdrant_search(project_id, message, top_k=5)
    except Exception:
        rag = []
    rag_context = "\n\n".join(rag)[:3000]

    template = await _get_prompt(project_id, "codegen.chat")
    sp = _safe_format(
        template,
        project_name=proj.get("name", ""),
        file_path=file_path or "(no file selected)",
        current_content=(file_doc.get("content", "") if file_doc else "")[:6000],
        related_context=related_context[:5000],
        rag_context=rag_context,
        message=message,
    )

    if not conv_id:
        conv_id = __import__("uuid").uuid4().hex
        await conversations.insert_one({"id": conv_id, "project_id": project_id, "stage": "CodeGen",
                                        "created_at": datetime.now(timezone.utc).isoformat()})
    await messages_col.insert_one({
        "id": __import__("uuid").uuid4().hex, "conversation_id": conv_id, "project_id": project_id,
        "role": "user", "content": message, "created_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        r = await chat_completion(
            messages=[{"role": "system", "content": sp}, {"role": "user", "content": message}],
            model=model, temperature=0.15, max_tokens=6000, timeout=180.0,
        )
    except Exception as e:
        raise HTTPException(502, f"LLM failed: {e}")
    content = r.get("content", "") or ""

    file_changes = []
    for m in re.finditer(r"\[FILE_CHANGE:([^\]]+)\]\s*(.*?)\s*\[/FILE_CHANGE\]", content, re.DOTALL):
        path = m.group(1).strip()
        new_content = m.group(2).strip()
        target = await codegen_files.find_one({"project_id": project_id, "file_path": path}, {"_id": 0})
        file_changes.append({
            "file_id": (target or {}).get("id"),
            "file_path": path,
            "old_content": (target or {}).get("content", ""),
            "new_content": new_content,
        })

    msg_id = __import__("uuid").uuid4().hex
    await messages_col.insert_one({
        "id": msg_id, "conversation_id": conv_id, "project_id": project_id,
        "role": "assistant", "content": content, "model": model,
        "tokens": r.get("usage", {}).get("total_tokens", 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"conversation_id": conv_id, "message_id": msg_id, "content": content, "file_changes": file_changes}


@router.post("/{project_id}/apply-file-change")
async def apply_file_change(project_id: str, payload: dict):
    file_id = payload.get("file_id")
    new_content = payload.get("new_content", "")
    if not file_id:
        raise HTTPException(400, "file_id required")
    d = await codegen_files.find_one({"project_id": project_id, "id": file_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "File not found")
    now = datetime.now(timezone.utc).isoformat()
    await codegen_files.update_one(
        {"project_id": project_id, "id": file_id},
        {"$set": {"content": new_content, "version": d.get("version", 1) + 1,
                  "edited": True, "updated_at": now}},
    )
    await audit_log.insert_one({
        "action": "codegen.chat.apply",
        "project_id": project_id, "at": now,
        "details": {"file_path": d["file_path"], "msg_id": payload.get("conversation_message_id")},
    })
    return {"ok": True}


# Reset
@router.post("/{project_id}/reset")
async def reset_codegen(project_id: str):
    deleted = {
        "codegen_files": (await codegen_files.delete_many({"project_id": project_id})).deleted_count,
        "codegen_runs": (await codegen_runs.delete_many({"project_id": project_id})).deleted_count,
    }
    now = datetime.now(timezone.utc).isoformat()
    await stage_context_col.delete_one({"project_id": project_id, "stage": "CodeGen"})
    await projects.update_one(
        {"id": project_id},
        {"$set": {"stage_status.CodeGen": "available", "stage_status.Living": "locked", "updated_at": now}},
    )
    await audit_log.insert_one({"action": "codegen.reset", "project_id": project_id, "at": now, "details": deleted})
    return {"ok": True, "deleted": deleted}


# Freeze entire CodeGen → unlock Living
@router.post("/{project_id}/freeze")
async def freeze_codegen(project_id: str):
    files_count = await codegen_files.count_documents({"project_id": project_id})
    if files_count == 0:
        raise HTTPException(400, "Generate code first.")
    services = await arch_services.find({"project_id": project_id}, {"_id": 0}).to_list(100)
    backend_langs = sorted({s.get("backend_lang", "nodejs") for s in services if not s.get("frontend")})
    outputs = {
        "total_files": files_count,
        "services_generated": len(services),
        "frontend_framework": "react",
        "backend_langs": backend_langs,
        "zip_available": True,
    }
    sources = {"prompts_used": ["codegen.service", "codegen.frontend", "codegen.docs"]}
    await save_stage_context(project_id, "CodeGen", outputs, sources, frozen_by="user")
    now = datetime.now(timezone.utc).isoformat()
    await projects.update_one(
        {"id": project_id},
        {"$set": {"stage_status.CodeGen": "frozen", "stage_status.Living": "available", "updated_at": now}},
    )
    return {"ok": True}
