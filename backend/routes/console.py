"""Console — Model Fabric, Agent Fabric, Prompt Engineering, Token Usage."""
import time
import httpx
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Query

from db import (
    model_providers as mp_col,
    agent_configs as ac_col,
    token_usage_log as log_col,
    prompts as prompts_col,
    project_prompts,
    projects,
    kb_toon,
)
from fabric.model_fabric import (
    PROVIDER_PRESETS,
    AGENT_COMPLEXITY,
    setup_default_provider,
    detect_provider_from_key,
    fabric_chat,
    estimate_prompt_tokens,
    estimate_cost,
    resolve_model,
)

router = APIRouter(prefix="/console", tags=["console"])


def _mask_key(k: str) -> str:
    k = k or ""
    if len(k) < 8:
        return "***"
    return f"{k[:6]}...{k[-4:]}"


def _serialize_provider(p: Dict[str, Any]) -> Dict[str, Any]:
    p = {**p}
    p.pop("_id", None)
    p["api_key"] = _mask_key(p.get("api_key", ""))
    return p


# ── Providers ────────────────────────────────────────────────────────
@router.post("/providers/setup")
async def providers_setup(payload: dict):
    api_key = (payload or {}).get("api_key", "").strip()
    if not api_key and (payload or {}).get("provider_type") != "ollama":
        raise HTTPException(400, "api_key required")
    name = (payload or {}).get("name", "")
    base_url = (payload or {}).get("base_url", "")
    doc = await setup_default_provider(api_key, name=name, base_url=base_url)
    return {"ok": True, "provider": _serialize_provider(doc)}


@router.get("/providers")
async def list_providers():
    docs = await mp_col.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"providers": [_serialize_provider(d) for d in docs]}


@router.put("/providers/{provider_id}")
async def update_provider(provider_id: str, payload: dict):
    upd = {}
    for f in ("name", "base_url", "is_active"):
        if f in payload:
            upd[f] = payload[f]
    if "routing" in payload and isinstance(payload["routing"], dict):
        upd["routing"] = payload["routing"]
    if payload.get("is_default") is True:
        await mp_col.update_many({}, {"$set": {"is_default": False}})
        upd["is_default"] = True
    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    r = await mp_col.update_one({"id": provider_id}, {"$set": upd})
    if r.matched_count == 0:
        raise HTTPException(404, "Provider not found")
    doc = await mp_col.find_one({"id": provider_id}, {"_id": 0})
    return {"ok": True, "provider": _serialize_provider(doc)}


@router.put("/providers/{provider_id}/key")
async def update_provider_key(provider_id: str, payload: dict):
    api_key = (payload or {}).get("api_key", "").strip()
    if not api_key:
        raise HTTPException(400, "api_key required")
    now = datetime.now(timezone.utc).isoformat()
    r = await mp_col.update_one(
        {"id": provider_id},
        {"$set": {"api_key": api_key, "detected_from_key": api_key[:8] + "...", "updated_at": now}},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Provider not found")
    return {"ok": True}


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str):
    active_count = await mp_col.count_documents({"is_active": True})
    target = await mp_col.find_one({"id": provider_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Provider not found")
    if target.get("is_active") and active_count <= 1:
        raise HTTPException(400, "Cannot delete the last active provider.")
    await mp_col.delete_one({"id": provider_id})
    if target.get("is_default"):
        # Promote the next active provider as default
        nxt = await mp_col.find_one({"is_active": True}, {"_id": 0}, sort=[("created_at", -1)])
        if nxt:
            await mp_col.update_one({"id": nxt["id"]}, {"$set": {"is_default": True}})
    return {"ok": True}


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: str):
    p = await mp_col.find_one({"id": provider_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Provider not found")
    ptype = p.get("provider_type", "openrouter")
    base_url = p.get("base_url", "")
    api_key = p.get("api_key", "")
    model_id = (p.get("routing") or {}).get("low") or (p.get("models") or [{}])[0].get("id", "")
    if not model_id:
        return {"ok": False, "error": "No model configured for this provider."}
    if ptype == "anthropic":
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
    elif ptype == "ollama":
        headers = {"Content-Type": "application/json"}
    else:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                   "HTTP-Referer": "https://lama.local", "X-Title": "LAMA"}
    payload = {"model": model_id,
               "messages": [{"role": "user", "content": "Say 'ok' in one word."}],
               "max_tokens": 10, "temperature": 0.1}
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            latency_ms = int((time.time() - t0) * 1000)
            if r.status_code != 200:
                return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}",
                        "latency_ms": latency_ms, "model_used": model_id}
            data = r.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"ok": True, "model_used": model_id, "latency_ms": latency_ms, "response": content[:100]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "latency_ms": int((time.time() - t0) * 1000), "model_used": model_id}


@router.post("/providers/{provider_id}/fetch-models")
async def fetch_provider_models(provider_id: str):
    p = await mp_col.find_one({"id": provider_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Provider not found")
    ptype = p.get("provider_type", "openrouter")
    base_url = p.get("base_url", "")
    api_key = p.get("api_key", "")
    if ptype == "anthropic":
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        url = f"{base_url}/models"
    elif ptype == "ollama":
        headers = {}
        url = f"{base_url.replace('/v1', '')}/api/tags"
    else:
        headers = {"Authorization": f"Bearer {api_key}"}
        url = f"{base_url}/models"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                return {"ok": False, "error": f"HTTP {r.status_code}"}
            data = r.json()
            raw = data.get("data") or data.get("models") or []
            models = []
            for m in raw:
                mid = m.get("id") or m.get("name") or ""
                if mid:
                    models.append({"id": mid, "label": mid})
            if models:
                await mp_col.update_one({"id": provider_id}, {"$set": {"models": models,
                                                                       "updated_at": datetime.now(timezone.utc).isoformat()}})
            return {"ok": True, "models": models, "count": len(models)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.get("/models/available")
async def list_available_models():
    docs = await mp_col.find({"is_active": True}, {"_id": 0}).to_list(50)
    out = []
    for p in docs:
        for m in p.get("models", []):
            out.append({"provider_id": p["id"], "provider_name": p.get("name", ""),
                        "provider_type": p.get("provider_type", ""),
                        "model_id": m.get("id", ""), "label": m.get("label", m.get("id", ""))})
    return {"models": out}


# ── Agents ───────────────────────────────────────────────────────────
STAGES_ORDER = ["Discovery", "DataModel", "Architecture", "CodeGen", "Living"]


@router.get("/agents")
async def list_agents():
    docs = await ac_col.find({}, {"_id": 0}).to_list(200)
    grouped = {s: {"orchestrator": [], "tasks": []} for s in STAGES_ORDER}
    for a in docs:
        stage = a.get("stage", "Discovery")
        grouped.setdefault(stage, {"orchestrator": [], "tasks": []})
        bucket = "orchestrator" if a.get("agent_type") == "orchestrator" else "tasks"
        grouped[stage][bucket].append(a)
    # Compute resolved model for each agent for display
    default_provider = await mp_col.find_one({"is_default": True, "is_active": True}, {"_id": 0})
    for stage in grouped.values():
        for bucket in stage.values():
            for a in bucket:
                if a.get("model_override"):
                    a["resolved_model"] = a["model_override"]
                elif default_provider:
                    a["resolved_model"] = (default_provider.get("routing") or {}).get(a.get("complexity", "medium"), "")
                else:
                    a["resolved_model"] = ""
                a["resolved_provider"] = (default_provider or {}).get("name", "(none)")
    return grouped


@router.get("/agents/{key}")
async def get_agent(key: str):
    a = await ac_col.find_one({"key": key}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Agent not found")
    return a


@router.put("/agents/{key}")
async def update_agent(key: str, payload: dict):
    upd: Dict[str, Any] = {}
    for f in ("status", "model_override", "provider_id", "max_tokens", "temperature",
              "wrap_prefix", "wrap_suffix", "replaced_template", "chain_to",
              "chain_condition", "token_budget_total", "complexity"):
        if f in payload:
            upd[f] = payload[f]
    if not upd:
        raise HTTPException(400, "Nothing to update")
    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    r = await ac_col.update_one({"key": key}, {"$set": upd})
    if r.matched_count == 0:
        raise HTTPException(404, "Agent not found")
    return {"ok": True}


@router.post("/agents/{key}/reset-budget")
async def reset_budget(key: str):
    r = await ac_col.update_one({"key": key}, {"$set": {"tokens_used_all_time": 0,
                                                        "updated_at": datetime.now(timezone.utc).isoformat()}})
    if r.matched_count == 0:
        raise HTTPException(404, "Agent not found")
    return {"ok": True}


@router.post("/agents/{key}/test")
async def test_agent(key: str, payload: dict):
    a = await ac_col.find_one({"key": key}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Agent not found")
    project_id = (payload or {}).get("project_id", "")
    test_message = (payload or {}).get("test_message",
                                       "Respond with one short sentence about your purpose.")
    sys_prompt = f"You are the LAMA agent '{a.get('label', key)}'. {a.get('description', '')}"
    if a.get("status") == "wrapped":
        sys_prompt = f"{a.get('wrap_prefix', '')}\n{sys_prompt}\n{a.get('wrap_suffix', '')}"
    elif a.get("status") == "replaced" and a.get("replaced_template"):
        sys_prompt = a["replaced_template"]
    try:
        r = await fabric_chat(
            messages=[{"role": "system", "content": sys_prompt},
                      {"role": "user", "content": test_message}],
            agent_key=key, project_id=project_id, timeout=60.0,
            max_tokens=min(a.get("max_tokens", 1024), 1024),
        )
        return {
            "ok": True,
            "content_preview": (r.get("content", "") or "")[:500],
            "usage": r.get("usage", {}),
            "cost_usd": r.get("cost_usd", 0.0),
            "model_used": r.get("model", ""),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:500]}


@router.get("/agents/{key}/usage")
async def agent_usage(key: str):
    a = await ac_col.find_one({"key": key}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Agent not found")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    cursor = log_col.find({"agent_key": key, "created_at": {"$gte": cutoff}}, {"_id": 0}).sort("created_at", -1)
    rows = await cursor.to_list(500)
    by_day: Dict[str, Dict[str, float]] = {}
    for r in rows:
        d = r.get("created_at", "")[:10]
        by_day.setdefault(d, {"tokens": 0, "cost": 0.0})
        by_day[d]["tokens"] += r.get("total_tokens", 0)
        by_day[d]["cost"] += r.get("cost_usd", 0.0)
    return {
        "last_run": {
            "tokens": a.get("tokens_used_last_run", 0),
            "model": a.get("last_run_model", ""),
            "cost_usd": a.get("last_run_cost_usd", 0.0),
            "at": a.get("last_run_at", ""),
        },
        "all_time_total": a.get("tokens_used_all_time", 0),
        "all_time_cost": sum(r.get("cost_usd", 0.0) for r in rows),
        "runs_last_7_days": [{"date": k, **v} for k, v in sorted(by_day.items())],
        "recent_runs": rows[:5],
    }


# ── Token usage reporting ────────────────────────────────────────────
@router.get("/usage/summary")
async def usage_summary(project_id: str = Query(default=""), days: int = Query(default=7)):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    q: Dict[str, Any] = {"created_at": {"$gte": cutoff}}
    if project_id:
        q["project_id"] = project_id
    rows = await log_col.find(q, {"_id": 0}).to_list(5000)
    total_tokens = sum(r.get("total_tokens", 0) for r in rows)
    total_cost = sum(r.get("cost_usd", 0.0) for r in rows)
    by_stage: Dict[str, Dict[str, Any]] = {}
    by_agent: Dict[str, Dict[str, Any]] = {}
    by_model: Dict[str, Dict[str, Any]] = {}
    by_day: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        s = r.get("stage") or "unknown"
        by_stage.setdefault(s, {"stage": s, "tokens": 0, "cost": 0.0})
        by_stage[s]["tokens"] += r.get("total_tokens", 0)
        by_stage[s]["cost"] += r.get("cost_usd", 0.0)
        ak = r.get("agent_key", "")
        by_agent.setdefault(ak, {"agent_key": ak, "label": ak, "tokens": 0, "cost": 0.0, "runs": 0})
        by_agent[ak]["tokens"] += r.get("total_tokens", 0)
        by_agent[ak]["cost"] += r.get("cost_usd", 0.0)
        by_agent[ak]["runs"] += 1
        m = r.get("model", "")
        by_model.setdefault(m, {"model": m, "tokens": 0, "cost": 0.0})
        by_model[m]["tokens"] += r.get("total_tokens", 0)
        by_model[m]["cost"] += r.get("cost_usd", 0.0)
        d = r.get("created_at", "")[:10]
        by_day.setdefault(d, {"date": d, "tokens": 0, "cost": 0.0})
        by_day[d]["tokens"] += r.get("total_tokens", 0)
        by_day[d]["cost"] += r.get("cost_usd", 0.0)
    return {
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 6),
        "total_runs": len(rows),
        "by_stage": list(by_stage.values()),
        "by_agent": list(by_agent.values()),
        "by_model": list(by_model.values()),
        "by_day": sorted(by_day.values(), key=lambda x: x["date"]),
    }


@router.get("/usage/log")
async def usage_log(project_id: str = Query(default=""), agent_key: str = Query(default=""),
                    limit: int = Query(default=50)):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if agent_key:
        q["agent_key"] = agent_key
    rows = await log_col.find(q, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 500))
    return {"logs": rows, "count": len(rows)}


# ── Prompt preview / test ────────────────────────────────────────────
async def _resolve_prompt_template(project_id: str, key: str) -> str:
    p = await project_prompts.find_one({"project_id": project_id, "key": key}, {"_id": 0})
    if p:
        return p["template"]
    g = await prompts_col.find_one({"key": key}, {"_id": 0})
    return g["template"] if g else ""


async def _resolve_variables(project_id: str, template: str) -> Dict[str, str]:
    import re
    var_names = sorted(set(re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", template)))
    proj = await projects.find_one({"id": project_id}, {"_id": 0}) if project_id else None
    toon_doc = await kb_toon.find_one({"project_id": project_id}, {"_id": 0}) if project_id else None
    toon_context = (toon_doc or {}).get("toon", "") if toon_doc else ""
    resolved: Dict[str, str] = {}
    for v in var_names:
        if v == "project_name" and proj:
            resolved[v] = proj.get("name", "")
        elif v == "source_tech" and proj:
            resolved[v] = proj.get("source_tech", "")
        elif v == "target_tech" and proj:
            resolved[v] = proj.get("target_tech", "")
        elif v == "toon_context":
            resolved[v] = toon_context[:6000]
        else:
            resolved[v] = f"<{v}>"  # placeholder
    return resolved


@router.post("/prompts/preview")
async def preview_prompt(payload: dict):
    key = (payload or {}).get("prompt_key", "")
    project_id = (payload or {}).get("project_id", "")
    if not key:
        raise HTTPException(400, "prompt_key required")
    template = await _resolve_prompt_template(project_id, key)
    if not template:
        raise HTTPException(404, "Prompt not found")
    resolved = await _resolve_variables(project_id, template)
    try:
        resolved_template = template.format(**resolved)
    except Exception as e:
        resolved_template = template + f"\n\n[render-error: {e}]"
    variables = [
        {"name": k, "resolved": (v or "")[:300], "token_estimate": max(1, len(v or "") // 4)}
        for k, v in resolved.items()
    ]
    total_tokens = sum(v["token_estimate"] for v in variables) + max(1, len(template) // 4)
    # Find model that will run for this key
    model_id, _, _ = await resolve_model(key)
    default_provider = await mp_col.find_one({"is_default": True}, {"_id": 0})
    ptype = (default_provider or {}).get("provider_type", "openrouter")
    cost = estimate_cost(model_id, total_tokens, 0, ptype)
    return {
        "resolved_template": resolved_template[:8000],
        "variables": variables,
        "total_token_estimate": total_tokens,
        "cost_estimate_usd": round(cost, 6),
        "model_that_will_run": model_id,
    }


@router.post("/prompts/test")
async def test_prompt(payload: dict):
    key = (payload or {}).get("prompt_key", "")
    project_id = (payload or {}).get("project_id", "")
    model_override = (payload or {}).get("model_override", "")
    if not key:
        raise HTTPException(400, "prompt_key required")
    template = await _resolve_prompt_template(project_id, key)
    if not template:
        raise HTTPException(404, "Prompt not found")
    resolved = await _resolve_variables(project_id, template)
    try:
        system_prompt = template.format(**resolved)
    except Exception:
        system_prompt = template
    t0 = time.time()
    try:
        r = await fabric_chat(
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": "Run."}],
            agent_key=key, project_id=project_id, timeout=60.0,
            model_override=model_override, max_tokens=1024,
        )
        return {
            "ok": True,
            "content": (r.get("content", "") or "")[:4000],
            "usage": r.get("usage", {}),
            "cost_usd": r.get("cost_usd", 0.0),
            "model_used": r.get("model", ""),
            "duration_ms": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:500], "duration_ms": int((time.time() - t0) * 1000)}
