"""Backend interface. Everything above this boundary is backend-agnostic, so the
diffusion CLI can be swapped for an OpenAI-compatible endpoint via PROMPTGEN_BACKEND."""

from typing import Protocol


class LLMBackend(Protocol):
    async def generate(
        self, prompt: str, *, system: str | None = None, max_tokens: int = 2048
    ) -> str: ...

    async def shutdown(self) -> None: ...


class GenerationError(Exception):
    pass


def get_backend() -> "LLMBackend":
    from app import config

    if config.BACKEND == "diffusion-cnv":
        from app.llm.diffusion_cnv import DiffusionCnvBackend

        return DiffusionCnvBackend()
    if config.BACKEND == "diffusion-oneshot":
        from app.llm.diffusion_oneshot import DiffusionOneshotBackend

        return DiffusionOneshotBackend()
    if config.BACKEND == "openai":
        from app.llm.openai_compat import OpenAIBackend

        return OpenAIBackend()
    raise ValueError(f"Unknown PROMPTGEN_BACKEND: {config.BACKEND}")
