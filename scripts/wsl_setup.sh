#!/usr/bin/env bash
# wsl_setup.sh — runs INSIDE Ubuntu (WSL2). Idempotent.
# Installs OS deps + builds a Linux-native venv with the ML stack pinned to the
# same versions as the Windows venv (torch 2.6.0+cu124, transformers 5.12.1, ...).
# Reuses the model weights + packed shards on /mnt/e (no re-download).
set -euo pipefail

VENV="$HOME/venv-lm"

echo "=== [1/4] OS deps ==="
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 python3-dev python3-venv python3-pip \
    build-essential cmake curl ca-certificates \
    libgomp1 libopenblas-dev 2>&1 | tail -3

echo "=== [2/4] venv at $VENV (Linux native FS) ==="
if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --upgrade pip wheel setuptools -q

echo "=== [3/4] ML stack (pinned to match Windows venv) ==="
"$VENV/bin/pip" install --no-cache-dir \
    torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124
"$VENV/bin/pip" install --no-cache-dir \
    "transformers==5.12.1" "peft==0.19.1" "accelerate==1.14.0" \
    "trl==1.7.0" "bitsandbytes==0.49.2" "sentencepiece==0.2.1" \
    datasets safetensors einops

echo "=== [4/4] sanity ==="
"$VENV/bin/python" - <<'PY'
import torch, transformers, peft, accelerate, trl, bitsandbytes
print("torch        ", torch.__version__, "| cuda?", torch.cuda.is_available(),
      "|", (torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NO GPU"))
print("transformers ", transformers.__version__)
print("peft         ", peft.__version__)
print("accelerate   ", accelerate.__version__)
print("trl          ", trl.__version__)
print("bitsandbytes ", bitsandbytes.__version__)
if torch.cuda.is_available():
    free, total = torch.cuda.mem_get_info()
    print(f"GPU VRAM free={free/1e9:.1f}GB total={total/1e9:.1f}GB")
PY

echo "=== sanity: assets on /mnt/e ==="
ls -d /mnt/e/local-model-run/models/Qwen2.5-Coder-32B-Instruct 2>/dev/null && echo "32B ok"
ls -d /mnt/e/local-model-run/data/packed 2>/dev/null && echo "packed ok"
ls /mnt/e/local-model-run/data/packed/shard_*.npy 2>/dev/null | wc -l | xargs echo "shard count:"

echo "=== DONE. venv at $VENV ==="
