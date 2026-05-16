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
