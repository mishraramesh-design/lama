"""Model Fabric — unified LLM client supporting any provider.

Key behaviours:
1. User pastes one API key → system auto-detects provider and sets up
   complexity routing automatically.
2. Every LLM call goes through resolve_model() which picks the right
   model based on agent complexity + provider routing.
3. Token usage is logged after every call.
4. Falls back to env-var config if no DB providers configured.
"""
import os
import time
import httpx
from typing import List, Dict, Tuple
from datetime import datetime, timezone


# ── Provider presets ──────────────────────────────────────────────────
PROVIDER_PRESETS: Dict[str, Dict] = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_prefix": "sk-or-",
        "default_models": {
            "low": "deepseek/deepseek-chat",
            "medium": "deepseek/deepseek-coder-v2",
            "high": "anthropic/claude-sonnet-4",
        },
        "model_catalogue": [
            {"id": "deepseek/deepseek-chat", "label": "DeepSeek Chat (low)",
             "context_window": 128000, "cost_per_1k_input": 0.00027, "cost_per_1k_output": 0.0011},
            {"id": "deepseek/deepseek-coder-v2", "label": "DeepSeek Coder V2 (medium)",
             "context_window": 128000, "cost_per_1k_input": 0.00014, "cost_per_1k_output": 0.00028},
            {"id": "qwen/qwen-2.5-72b-instruct", "label": "Qwen 2.5 72B (medium)",
             "context_window": 32000, "cost_per_1k_input": 0.00040, "cost_per_1k_output": 0.00040},
            {"id": "anthropic/claude-sonnet-4", "label": "Claude Sonnet 4 (high)",
             "context_window": 200000, "cost_per_1k_input": 0.003, "cost_per_1k_output": 0.015},
            {"id": "openai/gpt-4o", "label": "GPT-4o (high)",
             "context_window": 128000, "cost_per_1k_input": 0.005, "cost_per_1k_output": 0.015},
        ],
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "key_prefix": "sk-ant-",
        "default_models": {"low": "claude-haiku-4-5", "medium": "claude-sonnet-4", "high": "claude-sonnet-4"},
        "model_catalogue": [
            {"id": "claude-haiku-4-5", "label": "Claude Haiku (low)",
             "context_window": 200000, "cost_per_1k_input": 0.00025, "cost_per_1k_output": 0.00125},
            {"id": "claude-sonnet-4", "label": "Claude Sonnet 4 (high)",
             "context_window": 200000, "cost_per_1k_input": 0.003, "cost_per_1k_output": 0.015},
        ],
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "key_prefix": "sk-",
        "default_models": {"low": "gpt-4o-mini", "medium": "gpt-4o", "high": "gpt-4o"},
        "model_catalogue": [
            {"id": "gpt-4o-mini", "label": "GPT-4o Mini (low)",
             "context_window": 128000, "cost_per_1k_input": 0.00015, "cost_per_1k_output": 0.0006},
            {"id": "gpt-4o", "label": "GPT-4o (high)",
             "context_window": 128000, "cost_per_1k_input": 0.005, "cost_per_1k_output": 0.015},
        ],
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_prefix": "gsk_",
        "default_models": {"low": "llama-3.1-8b-instant", "medium": "llama-3.3-70b-versatile", "high": "llama-3.3-70b-versatile"},
        "model_catalogue": [
            {"id": "llama-3.1-8b-instant", "label": "Llama 3.1 8B (low)",
             "context_window": 128000, "cost_per_1k_input": 0.00005, "cost_per_1k_output": 0.00008},
            {"id": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B (medium/high)",
             "context_window": 128000, "cost_per_1k_input": 0.00059, "cost_per_1k_output": 0.00079},
        ],
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "key_prefix": "",
        "default_models": {"low": "llama3.2", "medium": "llama3.2", "high": "llama3.2"},
        "model_catalogue": [],
    },
    "custom": {
        "base_url": "",
        "key_prefix": "",
        "default_models": {"low": "", "medium": "", "high": ""},
        "model_catalogue": [],
    },
}


# ── Complexity map for all agent keys ────────────────────────────────
AGENT_COMPLEXITY: Dict[str, str] = {
    "srs.gap_question": "low", "srs.generate": "high", "srs.edit": "medium", "srs.diff": "medium",
    "datamodel.oltp": "high", "datamodel.olap": "medium", "datamodel.bus_matrix": "low", "datamodel.chat": "medium",
    "arch.recommend": "high", "arch.hld": "high", "arch.lld": "medium", "arch.sequence": "low",
    "arch.chat": "medium", "arch.decompose": "high",
    "codegen.service": "high", "codegen.frontend": "medium", "codegen.chat": "medium", "codegen.docs": "low",
    "orchestrator.discovery": "medium", "orchestrator.datamodel": "medium",
    "orchestrator.architecture": "medium", "orchestrator.codegen": "medium", "orchestrator.living": "medium",
}


def estimate_cost(model_id: str, prompt_tokens: int, completion_tokens: int,
                  provider_type: str = "openrouter") -> float:
    preset = PROVIDER_PRESETS.get(provider_type, {})
    for m in preset.get("model_catalogue", []):
        if m["id"] == model_id:
            return (prompt_tokens / 1000 * m["cost_per_1k_input"]
                    + completion_tokens / 1000 * m["cost_per_1k_output"])
    return 0.0


def detect_provider_from_key(api_key: str) -> str:
    key = (api_key or "").strip()
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith("sk-or-"):
        return "openrouter"
    if key.startswith("gsk_"):
        return "groq"
    if key.startswith("AIza"):
        return "google"
    if key.startswith("sk-"):
        return "openai"
    if not key:
        return "ollama"
    return "custom"


async def setup_default_provider(api_key: str, name: str = "", base_url: str = "") -> Dict:
    """Auto-configure a provider from a single API key. Called when user pastes a key in Console."""
    from db import model_providers as mp_col
    from models import ModelProvider
    provider_type = detect_provider_from_key(api_key)
    preset = PROVIDER_PRESETS.get(provider_type, PROVIDER_PRESETS["custom"])
    now = datetime.now(timezone.utc).isoformat()
    # Deactivate previous defaults
    await mp_col.update_many({}, {"$set": {"is_default": False}})
    doc = ModelProvider(
        name=name or f"{provider_type.title()} (auto)",
        provider_type=provider_type,
        base_url=base_url or preset["base_url"],
        api_key=api_key,
        is_default=True,
        detected_from_key=(api_key[:8] + "...") if api_key else "",
        models=preset.get("model_catalogue", []),
        routing=preset["default_models"].copy(),
    )
    d = doc.model_dump()
    d["updated_at"] = now
    # Always insert new (don't merge with same provider_type)
    await mp_col.insert_one(d)
    d.pop("_id", None)
    return d


async def resolve_model(agent_key: str) -> Tuple[str, str, Dict]:
    """Resolve which model and provider to use for an agent.
    Returns (model_id, provider_base_url, provider_headers).
    """
    from db import agent_configs as ac_col, model_providers as mp_col
    agent = await ac_col.find_one({"key": agent_key}, {"_id": 0})
    complexity = (agent or {}).get("complexity") or AGENT_COMPLEXITY.get(agent_key, "medium")
    model_override = (agent or {}).get("model_override", "")
    provider_id = (agent or {}).get("provider_id", "")
    provider = None
    if provider_id:
        provider = await mp_col.find_one({"id": provider_id, "is_active": True}, {"_id": 0})
    if not provider:
        provider = await mp_col.find_one({"is_default": True, "is_active": True}, {"_id": 0})

    if not provider:
        # Fallback to env vars (legacy OpenRouter)
        return (
            os.environ.get("LAMA_DEFAULT_MODEL", "deepseek/deepseek-chat"),
            os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            {
                "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://lama.local",
                "X-Title": "LAMA",
            },
        )

    model_id = (model_override
                or provider.get("routing", {}).get(complexity, "")
                or (provider.get("models") or [{}])[0].get("id", ""))
    ptype = provider.get("provider_type", "openrouter")
    base_url = provider.get("base_url", "")
    api_key = provider.get("api_key", "")
    if ptype == "anthropic":
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
    elif ptype == "ollama":
        headers = {"Content-Type": "application/json"}
    else:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://lama.local",
            "X-Title": "LAMA",
        }
    return model_id, base_url, headers


async def fabric_chat(
    messages: List[Dict],
    agent_key: str,
    project_id: str = "",
    model_override: str = "",
    max_tokens: int = 0,
    temperature: float = 0.3,
    timeout: float = 120.0,
) -> Dict:
    """Single entry point for all LLM calls. Resolves model, applies wraps, logs usage."""
    from db import agent_configs as ac_col, token_usage_log as log_col, model_providers as mp_col
    from models import TokenUsageLog
    now = datetime.now(timezone.utc).isoformat()
    agent = await ac_col.find_one({"key": agent_key}, {"_id": 0})
    status = (agent or {}).get("status", "enabled")
    if status == "disabled":
        return {
            "content": "", "model": "disabled",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "cost_usd": 0.0, "skipped": True,
        }

    if model_override:
        _, base_url, headers = await resolve_model(agent_key)
        model_id = model_override
    else:
        model_id, base_url, headers = await resolve_model(agent_key)

    # Apply wrap prefix/suffix to first system message
    if status == "wrapped" and agent:
        prefix = agent.get("wrap_prefix", "")
        suffix = agent.get("wrap_suffix", "")
        new_messages = []
        wrapped = False
        for msg in messages:
            if not wrapped and msg.get("role") == "system":
                new_messages.append({
                    "role": "system",
                    "content": f"{prefix}\n\n{msg['content']}\n\n{suffix}".strip(),
                })
                wrapped = True
            else:
                new_messages.append(msg)
        messages = new_messages

    # Token budget
    budget = (agent or {}).get("token_budget_total", 0)
    used = (agent or {}).get("tokens_used_all_time", 0)
    if budget > 0 and used >= budget:
        raise RuntimeError(
            f"Agent '{agent_key}' has exceeded token budget ({used}/{budget}). "
            "Reset in Console → Agents."
        )

    effective_max = max_tokens or (agent or {}).get("max_tokens", 4096)
    payload = {"model": model_id, "messages": messages, "temperature": temperature, "max_tokens": effective_max}
    t0 = time.time()
    error_msg = ""
    call_status = "success"
    content = ""
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            if resp.status_code != 200:
                call_status = "error"
                error_msg = f"HTTP {resp.status_code}: {resp.text[:300]}"
                raise RuntimeError(error_msg)
            data = resp.json()
            choice = data["choices"][0]
            content = choice["message"]["content"] or ""
            raw_usage = data.get("usage", {})
            usage = {
                "prompt_tokens": raw_usage.get("prompt_tokens", 0),
                "completion_tokens": raw_usage.get("completion_tokens", 0),
                "total_tokens": raw_usage.get("total_tokens", 0),
            }
    except httpx.TimeoutException:
        call_status = "timeout"
        error_msg = f"Request timed out after {timeout}s"
        raise RuntimeError(f"Agent '{agent_key}' timed out after {timeout}s")
    finally:
        duration_ms = int((time.time() - t0) * 1000)
        provider = await mp_col.find_one({"is_default": True}, {"_id": 0})
        ptype = (provider or {}).get("provider_type", "openrouter")
        cost = estimate_cost(model_id, usage["prompt_tokens"], usage["completion_tokens"], ptype)
        log = TokenUsageLog(
            project_id=project_id, agent_key=agent_key,
            stage=(agent or {}).get("stage", ""),
            model=model_id, provider_type=ptype,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            cost_usd=cost, duration_ms=duration_ms,
            status=call_status, error=error_msg,
        )
        try:
            await log_col.insert_one(log.model_dump())
        except Exception:
            pass
        if agent:
            try:
                await ac_col.update_one(
                    {"key": agent_key},
                    {"$set": {
                        "tokens_used_last_run": usage["total_tokens"],
                        "tokens_used_all_time": used + usage["total_tokens"],
                        "last_run_at": now, "last_run_model": model_id,
                        "last_run_input_tokens": usage["prompt_tokens"],
                        "last_run_output_tokens": usage["completion_tokens"],
                        "last_run_cost_usd": cost, "updated_at": now,
                    }},
                )
            except Exception:
                pass

    return {"content": content, "model": model_id, "usage": usage, "cost_usd": cost, "skipped": False}


def estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def estimate_prompt_tokens(messages: List[Dict]) -> int:
    total = sum(estimate_tokens(m.get("content", "")) for m in messages)
    return total + 4 * len(messages)
