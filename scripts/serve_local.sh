#!/usr/bin/env bash
# Launch a local vLLM server for OptionPilot dev (zero-cost, no API key).
#
# Serves Qwen3-Coder-30B-A3B (FP8) on a single RTX Pro 6000 (fits in 96GB, no tensor-parallel
# overhead; the second card stays free). Caches live on /media/user/data2 to spare the root disk.
#
# Then point OptionPilot at it (.env):
#   OPTIONPILOT_MODEL=hosted_vllm/Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8
#   OPTIONPILOT_API_BASE=http://localhost:8000/v1
#   OPTIONPILOT_API_KEY=local
set -euo pipefail

BASE=/media/user/data2/chiehchi
export HF_HOME="$BASE/hf_cache"
export VLLM_API_KEY="${VLLM_API_KEY:-local}"
# This box mixes Blackwell + 3090s; pin device order so GPU index matches nvidia-smi.
export CUDA_DEVICE_ORDER=PCI_BUS_ID
# System nvcc is 12.2 (can't JIT Blackwell sm_120). Disable FlashInfer's JIT sampler and
# use the bundled FlashAttention backend instead, so no on-the-fly compilation is needed.
export VLLM_USE_FLASHINFER_SAMPLER=0
export VLLM_ATTENTION_BACKEND=FLASH_ATTN

MODEL="${MODEL:-Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8}"
PORT="${PORT:-8000}"
GPU="${GPU:-0}"
MAXLEN="${MAXLEN:-65536}"
TOOL_PARSER="${TOOL_PARSER:-qwen3_coder}"

source "$BASE/vllm-env/bin/activate"

CUDA_VISIBLE_DEVICES="$GPU" exec vllm serve "$MODEL" \
  --served-model-name "$MODEL" \
  --enable-auto-tool-choice \
  --tool-call-parser "$TOOL_PARSER" \
  --max-model-len "$MAXLEN" \
  --port "$PORT"
