# promptgen — BMAD-style mega-prompt wizard backed by DiffusionGemma via llama.cpp PR #24423
#
# Build:
#   podman build -t localhost/promptgen:v3 .
# Import into containerd (kubelet's namespace):
#   podman save --format oci-archive -o /tmp/promptgen.tar localhost/promptgen:v1
#   sudo ctr -n k8s.io images import /tmp/promptgen.tar
#
# PR_SHA is the pinned head of https://github.com/ggml-org/llama.cpp/pull/24423
# (draft PR, no llama-server support — we build llama-diffusion-cli only).
# Re-pin deliberately; never build from the moving PR head.
ARG PR_SHA=10a2613aa0b2686f7d0608520c4f0ea05219df03

FROM docker.io/nvidia/cuda:12.8.1-devel-ubuntu24.04 AS build
ARG PR_SHA
RUN apt-get update && apt-get install -y --no-install-recommends git cmake build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --filter=blob:none https://github.com/ggml-org/llama.cpp /src \
    && cd /src \
    && git fetch origin pull/24423/head \
    && git checkout ${PR_SHA}
# Carried patch 1: the diffusion example exposes no --reasoning/--chat-template-kwargs
# flags, and DiffusionGemma's hidden thought channel multiplies generation time
# (~3min vs ~30s per call). Gate thinking behind the DIFFUSION_NO_THINK env var.
RUN sed -i 's/inputs.add_generation_prompt = true;/inputs.add_generation_prompt = true;\n        if (getenv("DIFFUSION_NO_THINK")) { inputs.enable_thinking = false; }/' \
      /src/examples/diffusion/diffusion-cli.cpp \
    && grep -q "DIFFUSION_NO_THINK" /src/examples/diffusion/diffusion-cli.cpp
# Carried patch 2: multi-GPU support for the single-device diffusion features
# (prompt-KV store per layer device, sc_dev/sc_embT on the output device with
# VRAM-pressure fallback, device sampling on the logits-owning GPU, prefill
# logits only for the last row, soft-fail sampler scratch). Validated bit-exact
# vs host paths via DG_SC_CHECK / DG_DEVSAMPLE_CHECK on 2x RTX 5060 Ti.
# Private carried patch only — NOT for upstream (llama.cpp AGENTS.md policy).
COPY patches/multi-gpu-diffusion.patch /tmp/multi-gpu-diffusion.patch
RUN cd /src && git apply --check /tmp/multi-gpu-diffusion.patch && git apply /tmp/multi-gpu-diffusion.patch
# sm_120 = RTX 5060 Ti (Blackwell). Static libs so the runtime stage needs only the binary.
RUN cmake -B /src/build -S /src \
      -DGGML_CUDA=ON \
      -DCMAKE_CUDA_ARCHITECTURES=120 \
      -DBUILD_SHARED_LIBS=OFF \
      -DLLAMA_CURL=OFF \
      -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /src/build -j --target llama-diffusion-cli
# Guard against the known regression where --n-cpu-moe was silently dropped from the
# diffusion runner — without MoE CPU offload, Q4_K_M does not fit a 16GB card.
# No GPU at build time: satisfy the libcuda.so.1 link with the CUDA stub.
RUN ln -s /usr/local/cuda/lib64/stubs/libcuda.so /usr/local/cuda/lib64/stubs/libcuda.so.1 \
    && LD_LIBRARY_PATH=/usr/local/cuda/lib64/stubs /src/build/bin/llama-diffusion-cli --help 2>&1 | grep -q "n-cpu-moe"

FROM docker.io/nvidia/cuda:12.8.1-runtime-ubuntu24.04
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3.12 python3-pip libgomp1 \
    && rm -rf /var/lib/apt/lists/* && apt-get clean
COPY --from=build /src/build/bin/llama-diffusion-cli /usr/local/bin/llama-diffusion-cli
COPY requirements.txt /app/requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /app/requirements.txt
COPY app/ /app/app/
WORKDIR /app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
