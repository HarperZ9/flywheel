#!/usr/bin/env bash
# Download the 32B flagship base to E: via huggingface_hub. ~62 GB bf16.
# Pure network (no pip); runs concurrently with the 14B download + chain.
# Idempotent: snapshot_download resumes and skips complete files.
set -uo pipefail
RUN=/e/local-model-run
PY="$RUN/venv/Scripts/python.exe"
export HF_HOME='E:\local-model-run\hf-cache'
export TMP='E:\local-model-run\tmp'
export TEMP='E:\local-model-run\tmp'
mkdir -p "$RUN/tmp" "$RUN/logs" "$RUN/models"
LOG="$RUN/logs/download-32b.log"
{
  echo "=== $(date) download 32B START ==="
  "$PY" - <<'PYEOF'
from huggingface_hub import snapshot_download
p = snapshot_download(
    repo_id="Qwen/Qwen2.5-Coder-32B-Instruct",
    local_dir=r"E:\local-model-run\models\Qwen2.5-Coder-32B-Instruct",
    ignore_patterns=["*.pth", "*.gguf", "original/*", "*.bin"],
    max_workers=8,
)
print("downloaded to", p)
PYEOF
  echo "=== $(date) download 32B DONE rc=$? ==="
} >> "$LOG" 2>&1
