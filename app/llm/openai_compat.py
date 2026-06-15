"""Default backend: any OpenAI-compatible /v1/chat/completions endpoint
(Ollama, LM Studio, llama-server, vLLM, or OpenAI proper).

Endpoint/model/key are read from app.settings at call time, so changes made in
the UI take effect on the next generation without a restart.
"""

import asyncio
import logging

import httpx

from app import config, settings
from app.llm.base import GenerationError

log = logging.getLogger("promptgen.openai")


class OpenAIBackend:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.status = "ready"

    async def generate(
        self, prompt: str, *, system: str | None = None, max_tokens: int = 2048
    ) -> str:
        cfg = settings.current
        if not cfg.base_url:
            raise GenerationError(
                "No endpoint configured. Open Settings and set an OpenAI-compatible base URL."
            )
        if not cfg.model:
            raise GenerationError(
                "No model selected. Open Settings and choose a model for your endpoint."
            )
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        headers = {}
        if cfg.api_key:
            headers["Authorization"] = f"Bearer {cfg.api_key}"
        body = {
            "model": cfg.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if cfg.disable_thinking:
            # llama.cpp/Qwen-style reasoning models burn the budget on a hidden
            # think channel otherwise. OpenAI proper rejects this, so it is gated.
            body["chat_template_kwargs"] = {"enable_thinking": False}
        async with self._lock:
            self.status = "generating"
            try:
                async with httpx.AsyncClient(timeout=config.GEN_TIMEOUT) as client:
                    r = await client.post(
                        f"{cfg.base_url}/chat/completions",
                        json=body,
                        headers=headers,
                    )
                if r.status_code != 200:
                    raise GenerationError(f"upstream {r.status_code}: {r.text[:300]}")
                data = r.json()
                content = data["choices"][0]["message"]["content"] or ""
                if not content.strip():
                    raise GenerationError("upstream returned empty content")
                return content.strip()
            except httpx.RequestError as e:
                raise GenerationError(f"could not reach {cfg.base_url}: {e}")
            finally:
                self.status = "ready"

    async def shutdown(self) -> None:
        pass


async def list_models(base_url: str, api_key: str = "") -> list[str]:
    """GET {base_url}/models for the settings UI. Raises GenerationError on failure."""
    base_url = base_url.strip().rstrip("/")
    if not base_url:
        raise GenerationError("Enter a base URL first.")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{base_url}/models", headers=headers)
    except httpx.RequestError as e:
        raise GenerationError(f"could not reach {base_url}: {e}")
    if r.status_code != 200:
        raise GenerationError(f"upstream {r.status_code}: {r.text[:200]}")
    data = r.json()
    items = data.get("data", data) if isinstance(data, dict) else data
    ids = [m.get("id") for m in items if isinstance(m, dict) and m.get("id")]
    return sorted(ids)
