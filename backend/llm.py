"""OpenRouter LLM client (OpenAI-compatible HTTP API via httpx)."""
import os
import httpx
from typing import List, Dict, Optional

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

AVAILABLE_MODELS = [
    {"id": "deepseek/deepseek-chat", "label": "DeepSeek Chat", "default_for": ["srs", "analysis"]},
    {"id": "deepseek/deepseek-coder", "label": "DeepSeek Coder", "default_for": ["code"]},
    {"id": "qwen/qwen-2.5-72b-instruct", "label": "Qwen 2.5 72B", "default_for": ["fallback"]},
]


async def chat_completion(
    messages: List[Dict[str, str]],
    model: str = "deepseek/deepseek-chat",
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: float = 90.0,
) -> Dict:
    """Send a chat completion request to OpenRouter. Returns dict with `content` and `usage`."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not configured")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://lama.local",
        "X-Title": "LAMA",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"OpenRouter error {resp.status_code}: {resp.text}")
        data = resp.json()

    choice = data["choices"][0]
    content = choice["message"]["content"] or ""
    usage = data.get("usage", {})
    return {
        "content": content,
        "model": data.get("model", model),
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
    }


def estimate_tokens(text: str) -> int:
    """Rough token estimate (4 chars per token)."""
    return max(1, len(text) // 4)


async def fabric_call(
    messages: List[Dict],
    agent_key: str = "",
    project_id: str = "",
    **kwargs,
) -> Dict:
    """Drop-in replacement for chat_completion. Routes through Model Fabric if providers
    are configured, else falls back to legacy chat_completion. Accepts both
    `model=...` (legacy) and `model_override=...` kwargs.
    """
    # Infer agent_key from call stack if not provided
    if not agent_key:
        try:
            import inspect
            frame = inspect.currentframe().f_back
            mod = frame.f_globals.get("__name__", "")
            agent_key = {
                "routes.architecture": "arch.chat",
                "routes.codegen": "codegen.chat",
                "routes.datamodel": "datamodel.chat",
                "routes.srs": "srs.generate",
                "routes.chat": "srs.gap_question",
            }.get(mod, "unknown")
        except Exception:
            agent_key = "unknown"
    try:
        from db import model_providers as mp_col
        has_providers = await mp_col.count_documents({"is_active": True}) > 0
        if has_providers:
            from fabric.model_fabric import fabric_chat
            return await fabric_chat(
                messages=messages,
                agent_key=agent_key,
                project_id=project_id,
                model_override=kwargs.get("model_override", "") or kwargs.get("model", ""),
                max_tokens=kwargs.get("max_tokens", 0) or 0,
                temperature=kwargs.get("temperature", 0.3),
                timeout=kwargs.get("timeout", 120.0),
            )
    except Exception:
        pass
    model = kwargs.get("model_override") or kwargs.get("model", "deepseek/deepseek-chat")
    return await chat_completion(
        messages=messages, model=model,
        max_tokens=kwargs.get("max_tokens", 4096) or 4096,
        temperature=kwargs.get("temperature", 0.3),
        timeout=kwargs.get("timeout", 120.0),
    )
