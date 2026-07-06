#!/usr/bin/env bash
# Install the rest of the training stack once torch is present. Run AFTER
# install_torch.sh completes (transformers pulls torch as a peer, not a build dep).
set -uo pipefail
RUN=/e/local-model-run
PY="$RUN/venv/Scripts/python.exe"
export PIP_CACHE_DIR='E:\local-model-run\pip-cache'
export TMP='E:\local-model-run\tmp'
export TEMP='E:\local-model-run\tmp'
mkdir -p "$RUN/tmp" "$RUN/logs"
LOG="$RUN/logs/install-rest.log"
{
  echo "=== $(date) install rest START ==="
  "$PY" -m pip install \
      transformers peft trl accelerate datasets \
      bitsandbytes safetensors sentencepiece einops
  echo "=== $(date) pip rc=$? ==="
  "$PY" -c "import transformers,peft,trl,accelerate,datasets,bitsandbytes,safetensors,sentencepiece;print('stack ok: transformers',transformers.__version__,'peft',peft.__version__,'trl',trl.__version__,'bnb',bitsandbytes.__version__)"
  echo "=== $(date) install rest DONE (verify rc=$?) ==="
} >> "$LOG" 2>&1
