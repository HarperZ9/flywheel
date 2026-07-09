#!/usr/bin/env bash
# run_phase2_linux.sh — Linux (WSL2) launcher for Phase 2 QLoRA CPT.
# Mirrors run_phase2.sh but uses the Linux venv and /mnt/{c,e} paths.
# Reuses model weights + packed shards + HF cache on /mnt/e (no re-download).
# Pass --smoke for the 2-step VRAM-envelope test first.
set -uo pipefail

RUN=/mnt/e/local-model-run
PY="$HOME/venv-lm/bin/python"
SRC=/mnt/c/dev/local-model/train/qlora_cpt.py

# Keep large caches + HF_HOME on /mnt/e (model already downloaded there).
export HF_HOME="$RUN/hf-cache"
export HF_HUB_OFFLINE=1            # we have the model; refuse network fallback
export PIP_CACHE_DIR="$RUN/pip-cache"
export TMPDIR="$RUN/tmp"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export BITSANDBYTES_NOWELCOME=1
export TOKENIZERS_PARALLELISM=false

mkdir -p "$RUN/tmp" "$RUN/logs"

TAG=full
for arg in "$@"; do [ "$arg" = "--smoke" ] && TAG=smoke; done

# Model is configurable via MODEL_SIZE (14B|32B), default 32B. The 14B fits a
# single 4090 at seq_len 2048 (21 GB peak); the 32B needs the memory layer.
MODEL_SIZE="${MODEL_SIZE:-32B}"
case "$MODEL_SIZE" in
    14B) MODEL_DIR="Qwen2.5-Coder-14B-Instruct"; OUT_TAG="14b" ;;
    32B) MODEL_DIR="Qwen2.5-Coder-32B-Instruct"; OUT_TAG="32b" ;;
    *) echo "MODEL_SIZE must be 14B or 32B, got '$MODEL_SIZE'" >&2; exit 2 ;;
esac
LOG="$RUN/logs/phase2-linux-${OUT_TAG}-${TAG}.log"

# Linux-native checkpoint dir name so we never collide with Windows checkpoints.
COMMON_ARGS=(
    --model  "$RUN/models/$MODEL_DIR"
    --packed "$RUN/data/packed"
    --out    "$RUN/checkpoints/phase2-linux-qlora-cpt-${OUT_TAG}"
    --seq-len 2048
    --lora-r  16
    --lora-targets all
    --attn sdpa
)

{
    echo "=== $(date -u '+%Y-%m-%dT%H:%M:%SZ') phase2-linux ($TAG) START ==="
    "$PY" -u "$SRC" "${COMMON_ARGS[@]}" "$@"
    rc=$?
    echo "=== $(date -u '+%Y-%m-%dT%H:%M:%SZ') phase2-linux ($TAG) DONE rc=$rc ==="
} >> "$LOG" 2>&1
exit "$rc"
