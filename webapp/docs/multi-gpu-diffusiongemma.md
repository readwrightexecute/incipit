# DiffusionGemma on 2 GPUs in llama.cpp: re-enabling the three optimizations PR #24423 turns off

**TL;DR:** llama.cpp's DiffusionGemma PR ([#24423](https://github.com/ggml-org/llama.cpp/pull/24423)) silently disables its prompt-KV cache, device-resident self-conditioning, and GPU sampling whenever the model spans more than one CUDA device. We patched all three to be multi-GPU aware on a 2× RTX 5060 Ti (16GB) homelab box: **flat ~233ms/step regardless of context length**, vs 335ms/step degrading to 542ms/step stock, vs ~1200ms/step on a single 16GB card with CPU MoE offload. Correctness verified bit-exact with the PR's own debug validators. Patch below; not submitted upstream (see disclosure).

## Setup

| | |
|---|---|
| GPUs | 2× NVIDIA RTX 5060 Ti 16GB (Blackwell, sm_120), PCIe |
| Model | `diffusiongemma-26B-A4B-it` Q4_K_M GGUF (16.8GB, unsloth quant) |
| Base | PR #24423 @ `10a2613aa0b2686f7d0608520c4f0ea05219df03` (2026-06-11) |
| Split | `-ngl 99 -sm layer` (layer split; `-ts` ratio discussion below) |

A 16.8GB model doesn't fit one 16GB card, so your options are (a) one GPU + `--n-cpu-moe` expert offload — works, ~1.2s/step, or (b) split across both cards — and discover the PR degrades itself:

```
diffusion_eb: kv cache auto-off (2 GPUs; pass --diffusion-kv-cache on to force)
diffusion_eb: gpu sampling off (2 GPUs; sc_dev is single-device)
diffusion_eb: gpu sample reduce off (2 GPUs; needs a single CUDA device)
```

Three features, all hardcoded single-device (and for two of them, even explicit `on` was ignored). Without the prompt-KV cache every denoising step re-processes the full prompt, so multi-GPU step time *grows with context* — exactly when you need it not to.

## What the patch changes (5 files, +123/−62)

1. **Prompt-KV store → per-layer-device allocation.** The store kept all layers' F32 prompt K/V in one buffer on layer 0's device; the code comment itself said multi-GPU "would need a per-buft context map" — so that's what we built. Each layer's K/V now lives on the device that computes that layer: PREFILL writes and DECODE reads are all device-local.

2. **Self-conditioning buffers → output device, with a fallback chain.** `sc_dev` (prev-step canvas logits, written by lm_head) and `sc_embT` (1.3GB transposed embedding for the SC matmul) moved from layer-0's device to the last layer's device, where the logits are produced — the 256MB/step write becomes local and only a ~2.6MB soft-embedding crosses GPUs. Under VRAM pressure the allocation falls back last-device → first-device → host instead of asserting.

3. **CUDA sampler → runs on the device that owns the logits.** The kernel launch assumed "current device" (true only when gated to 1 GPU). Now resolves the owning device via `cudaPointerGetAttributes` and switches to it. Scratch buffers also soft-fail to the host sampling path on OOM instead of aborting the process.

4. **Prefill no longer materializes `[n_vocab × P]` logits.** The PREFILL batch marked every prompt row for logits output — at 262k vocab that's ~1MB *per prompt token* (4GB at a 4k prompt) allocated for data nobody reads. Now only the last row outputs. This one matters on a single GPU too.

5. **CLI gates honor explicit `on`** for multi-GPU; `auto` stays conservative (single-GPU only).

## Correctness

The PR ships its own validators, which made this easy to prove rather than vibe-check:

- `DG_SC_CHECK=1` (device SC buffer vs host logits): **`maxabs=0 sumabs=0 nmiss=0/67108864` on every step** — bit-identical on the 2-GPU split.
- `DG_DEVSAMPLE_CHECK=1` (device vs host sampling): **`amax_mismatch=0/256 tok_diff=0/256`** every step; entropy within documented FP-reduction tolerance (~1e-4).

## Performance (2× 5060 Ti, Q4_K_M, thinking disabled)

| Config | Short prompt | Long multi-block (6×256 tok) |
|---|---|---|
| 1 GPU + `--n-cpu-moe` (16GB-card config from the PR thread) | ~1100–1670 ms/step | — |
| 2 GPU stock (features auto-off) | 335 ms/step | degrades to **542 ms/step** by block 5 |
| **2 GPU patched (all three on)** | **217 ms/step** | **flat 233 ms/step**, 55 tok/s effective |

The headline isn't just the 1.5× on short prompts — it's that step time stops growing with context, because the prompt prefix is finally cached across denoising steps on multi-GPU.

## Caveats / tuning notes (the OOM diary)

- **The reserve compute buffer lands on the lm_head GPU and scales with `n_ubatch`**, which the CLI auto-grows from `-n` (`blocks×256 + 2048`). At `-n 2048` that's a ~6GB worst-case reservation on one card. Keep `-n` honest, and use an asymmetric `-ts` that keeps the lm_head GPU light (we run `-ts 7,3`).
- ggml's VMM pool growth (`cuMemCreate`) hard-aborts on OOM with no fallback — if you're within ~1GB of full on the lm_head card, a long-context generation can still kill the process. Leave margin for whatever else shares the card.
- Tested on exactly one topology: 2× identical 16GB cards, layer split. Row split, >2 GPUs, and mixed-VRAM setups are unvalidated.
- Thinking disabled via a separate one-line patch (`enable_thinking=false` env gate) — the diffusion example exposes no `--reasoning` flag; the hidden thought channel otherwise dominates generation time.

## Disclosure & why this isn't a PR

This patch was developed by an AI coding agent (Claude Fable 5, via Claude Code) working in a homelab, directed and tested by a human. llama.cpp's contribution policy prohibits predominantly AI-generated PRs and instructs autonomous agents not to submit — so this stays a private carried patch, published here as findings. If the PR author or any human contributor wants to reimplement these changes with full understanding (the per-buft KV map is even pre-described in their own code comment), everything needed is in this writeup and the diff. Related known issue: a commenter on #24423 already reported device sampling silently disabling on multi-GPU setups.

Patch: `multi-gpu-diffusion.patch` (318 lines, applies clean on `10a2613a`).
