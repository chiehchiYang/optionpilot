#!/usr/bin/env bash
# Build the local vLLM venv that works on this box (driver 570 / CUDA 12.8, RTX Pro 6000
# Blackwell). Kept separate from the OptionPilot project venv to avoid dependency conflicts.
#
# Why the pins:
#   - Driver 570 supports CUDA 12.8, NOT 13. The default vLLM pulls torch cu130 (CUDA 13),
#     whose kernels need driver >=580 -> "libcudart.so.13" error. We pin torch==2.8.0 (a
#     cu128-only series) so uv resolves the matching cu128-built vLLM (0.11.0).
#   - transformers must stay <5: vLLM 0.11.0 breaks on transformers 5.x
#     ("Qwen2Tokenizer has no attribute all_special_tokens_extended").
# Runtime quirks (handled in serve_local.sh): FlashInfer JIT sampler is disabled because the
# system nvcc (12.2) can't compile Blackwell sm_120; FlashAttention backend is used instead.
set -euo pipefail

BASE=/media/user/data2/chiehchi
export UV_CACHE_DIR="$BASE/.uv_cache"
export TMPDIR="$BASE/vllm_tmp"
mkdir -p "$UV_CACHE_DIR" "$TMPDIR" "$BASE/hf_cache"

uv venv --python 3.12 "$BASE/vllm-env"
source "$BASE/vllm-env/bin/activate"

uv pip install "vllm" "torch==2.8.0" --torch-backend=cu128
uv pip install "transformers<5"

python -c "import torch, vllm, transformers; print('vllm', vllm.__version__, '| torch', torch.__version__, '| transformers', transformers.__version__)"
python -c "import vllm._C; print('vllm._C kernels import OK')"
echo "Done. Launch the server with: bash scripts/serve_local.sh"
