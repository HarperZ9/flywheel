#!/usr/bin/env bash
# Download the base model to E: via huggingface_hub. Long pole #2.
# Pure network (no pip), so it can run concurrently with the torch install.
# Idempotent: snapshot_download resumes and skips already-complete files.
set -uo pipefail
RUN=/e/local-model-run
PY="$RUN/venv/Scripts/python.exe"
export HF_HOME='E:\local-model-run\hf-cache'
# hf_hub 1.x uses the hf-xet accelerated backend by default; do NOT set
# HF_HUB_ENABLE_HF_TRANSFER (the legacy hf_transfer pkg is not installed and
# the flag would hard-error at startup).
export TMP='E:\local-model-run\tmp'
export TEMP='E:\local-model-run\tmp'
mkdir -p "$RUN/tmp" "$RUN/logs" "$RUN/models"
LOG="$RUN/logs/download-base.log"
{
  echo "=== $(date) download base START ==="
  "$PY" - <<'PYEOF'
from huggingface_hub import snapshot_download
p = snapshot_download(
    repo_id="Qwen/Qwen2.5-Coder-14B-Instruct",
    local_dir=r"E:\local-model-run\models\Qwen2.5-Coder-14B-Instruct",
    # safetensors only; skip torch .pth, GGUF, and any 'original/' duplicates
    ignore_patterns=["*.pth", "*.gguf", "original/*", "*.bin"],
    max_workers=8,
)
print("downloaded to", p)
PYEOF
  echo "=== $(date) download base DONE rc=$? ==="
} >> "$LOG" 2>&1
