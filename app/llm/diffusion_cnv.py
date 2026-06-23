"""Primary backend: a persistent `llama-diffusion-cli -cnv` subprocess.

Protocol (verified against PR #24423 @ 10a2613, examples/diffusion/diffusion-cli.cpp):
- Ready/turn marker: `printf("\\n> ")` on stdout, async logs flushed first.
- Input: `std::getline` — strictly one line per turn, so prompts are flattened
  (literal "\\n" markers; the system prompt explains them).
- Response: LOG("\\n%s\\n") on stdout, followed by `total time:`/`throughput:`
  timing lines, then the next marker. Info/load logs go to stderr. No echo.
- `/clear` resets history but keeps the system prompt; `-sys` sets it at spawn.

The process is spawned lazily on first use and killed after IDLE_TIMEOUT to
release ~14GB of VRAM (llama-swap-style ttl).
"""

import asyncio
import logging
import os
import re
from collections import deque

from app import config
from app.llm.base import GenerationError

log = logging.getLogger("promptgen.cnv")

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b[()][0-9A-B]")
TIMING_RE = re.compile(r"^(total time:|throughput:|conversation history cleared)", re.M)
# End-of-generation timing lines the CLI prints right before the next prompt
# marker. Used to disambiguate the real marker from an in-content markdown
# blockquote line ("> ") that a chunk happens to pause on mid-generation.
GEN_DONE_RE = re.compile(r"^(total time:|throughput:)", re.M)
SETTLE_SECONDS = 1.0
MARKER = "\n> "


def clean_output(raw: str) -> str:
    """Strip ANSI sequences and resolve carriage-return overwrites."""
    s = ANSI_RE.sub("", raw)
    return "\n".join(line.split("\r")[-1] for line in s.split("\n"))


class DiffusionCnvBackend:
    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._idle_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._system: str | None = None
        self._max_tokens: int | None = None
        self._stderr_tail: deque[str] = deque(maxlen=40)
        self.status = "cold"  # cold | loading | ready | generating

    def _build_cmd(self, max_tokens: int) -> list[str]:
        cmd = [
            config.CLI_BIN,
            "-m", config.MODEL_PATH,
            "-ngl", config.N_GPU_LAYERS,
            "--n-cpu-moe", config.N_CPU_MOE,
            "-cnv",
            "-n", str(max_tokens),
            "--threads", config.THREADS,
            *config.DIFFUSION_ARGS,
        ]
        if self._system:
            cmd += ["-sys", self._system]
        return cmd

    async def _ensure_proc(self, max_tokens: int) -> asyncio.subprocess.Process:
        if self._proc is not None and self._proc.returncode is None:
            return self._proc
        self.status = "loading"
        cmd = self._build_cmd(max_tokens)
        log.info("spawning llama-diffusion-cli (model load may take minutes)")
        self._stderr_tail.clear()
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # Inherit pod env (CUDA_VISIBLE_DEVICES pins the GPU) and force a
                # dumb terminal so the CLI emits no ANSI.
                env={**os.environ, "TERM": "dumb", "NO_COLOR": "1"},
            )
        except (FileNotFoundError, OSError) as e:
            self.status = "cold"
            raise GenerationError(f"could not spawn {config.CLI_BIN}: {e}")
        # Keep a reference: a bare create_task() may be garbage-collected mid-run.
        self._stderr_task = asyncio.create_task(self._drain_stderr(self._proc))
        try:
            await self._read_until_marker(timeout=config.LOAD_TIMEOUT)
        except Exception:
            tail = self._errors_tail()
            await self.shutdown()
            raise GenerationError(f"model load failed or timed out: {tail}")
        self.status = "ready"
        self._max_tokens = max_tokens
        return self._proc

    async def _drain_stderr(self, proc: asyncio.subprocess.Process) -> None:
        """Keep the last stderr lines for error reporting (and the pod log)."""
        assert proc.stderr is not None
        while True:
            line = await proc.stderr.readline()
            if not line:
                return
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                self._stderr_tail.append(text)

    def _errors_tail(self) -> str:
        # E-level lines are the diagnosis (e.g. cudaMalloc out of memory);
        # fall back to the last few raw lines.
        errs = [ln for ln in self._stderr_tail if " E " in ln or "error" in ln.lower()]
        tail = errs[-3:] if errs else list(self._stderr_tail)[-3:]
        return " | ".join(tail) if tail else "(no stderr captured)"

    async def _read_until_marker(self, timeout: float,
                                 require_timing: bool = False) -> str:
        """Read stdout until the cleaned buffer ends with the turn marker
        ('\\n> ') and output has settled for SETTLE_SECONDS.

        When require_timing is set (a real generation), also require the CLI's
        end-of-generation timing line ('total time:'/'throughput:') to have
        appeared first. Otherwise a response whose chunk ends on a markdown
        blockquote line ('> ') during a settle pause would be mistaken for the
        prompt marker and truncated."""
        assert self._proc is not None and self._proc.stdout is not None
        buf = b""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise GenerationError("generation timed out")
            try:
                chunk = await asyncio.wait_for(
                    self._proc.stdout.read(4096), timeout=min(remaining, SETTLE_SECONDS)
                )
                if not chunk:  # EOF — process died
                    raise GenerationError(
                        f"llama-diffusion-cli exited (rc={self._proc.returncode}): "
                        f"{self._errors_tail()}"
                    )
                buf += chunk
            except asyncio.TimeoutError:
                # No new bytes for a settle window — check for the marker.
                text = clean_output(buf.decode("utf-8", errors="replace"))
                if text.endswith(MARKER) and (
                    not require_timing or GEN_DONE_RE.search(text)
                ):
                    return text

    async def _write_line(self, line: str) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        self._proc.stdin.write((line + "\n").encode())
        await self._proc.stdin.drain()

    def _arm_idle_timer(self) -> None:
        if self._idle_task is not None:
            self._idle_task.cancel()
        self._idle_task = asyncio.create_task(self._idle_kill())

    async def _idle_kill(self) -> None:
        try:
            await asyncio.sleep(config.IDLE_TIMEOUT)
        except asyncio.CancelledError:
            return
        log.info("idle timeout reached — releasing model")
        async with self._lock:
            await self.shutdown()

    async def generate(
        self, prompt: str, *, system: str | None = None, max_tokens: int = 2048
    ) -> str:
        # System prompt is fixed at spawn time via -sys; all callers pass the
        # same one (flow.SYSTEM). A changed non-None system forces a respawn;
        # system=None (party mode) intentionally reuses the running process.
        # The CLI also receives -n only at spawn, so token-limit changes respawn.
        token_limit = min(max_tokens, config.MAX_TOKENS)
        flat = prompt.replace("\r", " ").replace("\n", "\\n")
        async with self._lock:
            if self._idle_task is not None:
                self._idle_task.cancel()
            try:
                if system and system != self._system:
                    if self._proc is not None:
                        await self.shutdown()
                    self._system = system
                if token_limit != self._max_tokens:
                    if self._proc is not None:
                        await self.shutdown()
                await self._ensure_proc(token_limit)
                self.status = "generating"
                await self._write_line("/clear")
                await self._read_until_marker(timeout=30)
                await self._write_line(flat)
                raw = await self._read_until_marker(timeout=config.GEN_TIMEOUT,
                                                    require_timing=True)
            except GenerationError:
                await self.shutdown()
                raise
            finally:
                if self._proc is not None and self._proc.returncode is None:
                    self.status = "ready"
                else:
                    self.status = "cold"
                self._arm_idle_timer()
        return self._extract_response(raw)

    @staticmethod
    def _extract_response(cleaned: str) -> str:
        text = cleaned
        if text.endswith(MARKER):
            text = text[: -len(MARKER)]
        # Drop timing/housekeeping lines emitted after the response.
        lines = [ln for ln in text.split("\n") if not TIMING_RE.match(ln)]
        text = "\n".join(lines)
        # DiffusionGemma emits '<|channel>thought ... <channel|>answer' —
        # keep only what follows the last channel close (verified in smoke test).
        if "<channel|>" in text:
            text = text.rsplit("<channel|>", 1)[1]
        text = re.sub(r"<\|?think\|?>.*?<\|?/think\|?>", "", text, flags=re.S)
        return text.strip()

    async def shutdown(self) -> None:
        proc, self._proc = self._proc, None
        self._max_tokens = None
        self.status = "cold"
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            self._stderr_task = None
        if proc is None or proc.returncode is not None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.write(b"/exit\n")
                await proc.stdin.drain()
            await asyncio.wait_for(proc.wait(), timeout=10)
        except Exception:
            proc.kill()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except Exception:
                pass
