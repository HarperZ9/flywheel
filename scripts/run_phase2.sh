#!/usr/bin/env bash
# Launch Phase 2 QLoRA continued-pretraining. Pass --smoke for the 2-step
# VRAM-envelope test first. Everything logs to E:.
set -uo pipefail
RUN=/e/local-model-run
PY="$RUN/venv/Scripts/python.exe"
export HF_HOME='E:\local-model-run\hf-cache'
export PIP_CACHE_DIR='E:\local-model-run\pip-cache'
export TMP='E:\local-model-run\tmp'
export TEMP='E:\local-model-run\tmp'
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export BITSANDBYTES_NOWELCOME=1
mkdir -p "$RUN/tmp" "$RUN/logs"
# derive a log tag from the args without consuming them
TAG=full
for arg in "$@"; do [ "$arg" = "--smoke" ] && TAG=smoke; done
LOG="$RUN/logs/phase2-${TAG}.log"
{
  echo "=== $(date) phase2 ($TAG) START ==="
  # Windows venv python needs a Windows-form script path, not an MSYS /c/ path
  "$PY" "C:/dev/local-model/train/qlora_cpt.py" "$@"
  echo "=== $(date) phase2 ($TAG) DONE rc=$? ==="
} >> "$LOG" 2>&1
