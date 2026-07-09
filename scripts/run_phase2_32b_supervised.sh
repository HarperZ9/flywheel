#!/usr/bin/env bash
# run_phase2_32b_supervised.sh — supervised, resumable 32B QLoRA CPT launch.
#
# The 32B smoke PASSED in WSL (2026-07-06: peak 21.24 GB, free 1.8 GB, rc=0,
# seq_len 256), but WSL CUDA occasionally dies with "device not ready".
# This wrapper relaunches with --resume after such deaths, bounded attempts,
# so a multi-hour run survives driver hiccups without human babysitting.
#
# Recipe parity with the shipped 14B artifact: checkpoint-2020 was ~2020
# optimizer steps. At this packing (258,432 seqs of 256 tokens, effective
# batch 32) one epoch is ~8,076 steps, so --epochs 0.25 lands ~2,019 steps.
# Checkpoints every 50 steps (trainer default) keep the run resumable.
#
# Usage (from WSL):   bash /mnt/c/dev/local-model/scripts/run_phase2_32b_supervised.sh
# Monitor:            tail -f /mnt/e/local-model-run/logs/phase2-linux-32b-full.log
#                     tail -f /mnt/e/local-model-run/logs/phase2-32b-supervisor.log
# Stop:               touch /mnt/e/local-model-run/STOP_32B  (checked between attempts)
#                     or kill the python process for an immediate stop.
set -uo pipefail

RUN=/mnt/e/local-model-run
SUP_LOG="$RUN/logs/phase2-32b-supervisor.log"
STOP_FILE="$RUN/STOP_32B"
MAX_ATTEMPTS=12
SEQ_LEN=256
EPOCHS=0.25

log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*" >> "$SUP_LOG"; }

mkdir -p "$RUN/logs"
log "supervisor start: MODEL_SIZE=32B seq_len=$SEQ_LEN epochs=$EPOCHS max_attempts=$MAX_ATTEMPTS"

attempt=0
resume_flag=""
# Resume immediately if a real (non-smoke) checkpoint already exists.
if ls "$RUN/checkpoints/phase2-linux-qlora-cpt-32b"/checkpoint-* >/dev/null 2>&1; then
    resume_flag="--resume"
    log "existing checkpoint found; starting with --resume"
fi

while [ "$attempt" -lt "$MAX_ATTEMPTS" ]; do
    if [ -f "$STOP_FILE" ]; then
        log "stop file present; exiting cleanly"
        exit 0
    fi
    attempt=$((attempt + 1))
    log "attempt $attempt/$MAX_ATTEMPTS (resume_flag='$resume_flag')"
    MODEL_SIZE=32B bash /mnt/c/dev/local-model/scripts/run_phase2_linux.sh \
        --seq-len "$SEQ_LEN" --epochs "$EPOCHS" $resume_flag
    rc=$?
    if [ "$rc" -eq 0 ]; then
        log "training completed with rc=0 after attempt $attempt"
        exit 0
    fi
    log "attempt $attempt died with rc=$rc; will resume from latest checkpoint"
    resume_flag="--resume"
    sleep 30
done

log "gave up after $MAX_ATTEMPTS attempts; inspect $RUN/logs/phase2-linux-32b-full.log"
exit 1
