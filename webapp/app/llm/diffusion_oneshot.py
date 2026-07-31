"""Fallback backend: one llama-diffusion-cli process per call (no -cnv).

Pays a full model load per call, but supports multi-line prompts cleanly via
-f and avoids all stdin-protocol fragility. Used if -cnv pipe-driving proves
unreliable (PROMPTGEN_BACKEND=diffusion-oneshot).
"""

import asyncio
import logging
import os
import re
import tempfile

from app import config
from app.llm.base import GenerationError
from app.llm.diffusion_cnv import clean_output

log = logging.getLogger("promptgen.oneshot")


class DiffusionOneshotBackend:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.status = "cold"

    async def generate(
        self, prompt: str, *, system: str | None = None, max_tokens: int = 2048
    ) -> str:
        full = f"{system.strip()}\n\n{prompt}" if system else prompt
        async with self._lock:
            self.status = "generating"
            fd, path = tempfile.mkstemp(suffix=".txt", dir="/tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    f.write(full)
                cmd = [
                    config.CLI_BIN,
                    "-m", config.MODEL_PATH,
                    "-ngl", config.N_GPU_LAYERS,
                    "--n-cpu-moe", config.N_CPU_MOE,
                    "-f", path,
                    "-n", str(min(max_tokens, config.MAX_TOKENS)),
                    "--threads", config.THREADS,
                    *config.DIFFUSION_ARGS,
                ]
                try:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env={**os.environ, "TERM": "dumb", "NO_COLOR": "1"},
                    )
                except (FileNotFoundError, OSError) as e:
                    raise GenerationError(f"could not spawn {config.CLI_BIN}: {e}")
                try:
                    out, err = await asyncio.wait_for(
                        proc.communicate(),
                        timeout=config.LOAD_TIMEOUT + config.GEN_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()  # reap the killed child (avoid a zombie)
                    raise GenerationError("one-shot generation timed out")
                if proc.returncode != 0:
                    tail = err.decode(errors="replace")[-500:]
                    raise GenerationError(f"cli rc={proc.returncode}: {tail}")
                text = clean_output(out.decode("utf-8", errors="replace"))
                # Output begins with the echoed prompt; drop it.
                if full in text:
                    text = text.split(full, 1)[1]
                if "<channel|>" in text:
                    text = text.rsplit("<channel|>", 1)[1]
                text = re.sub(r"<\|?think\|?>.*?<\|?/think\|?>", "", text, flags=re.S)
                # Drop trailing timing lines.
                text = "\n".join(
                    ln for ln in text.split("\n")
                    if not ln.startswith(("total time:", "throughput:"))
                )
                return text.strip()
            finally:
                self.status = "cold"
                try:
                    os.unlink(path)
                except OSError:
                    pass

    async def shutdown(self) -> None:
        pass
