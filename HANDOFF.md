# HANDOFF — local-model build (session continuation artifact)

> **Superseded by [PROJECT.md](PROJECT.md) + [STATE.md](STATE.md).** Historical Phase-2 handoff; treat its "pending" items as done.

> **Read this first.** Generated 2026-07-04 after a full session that
> (a) corrected the Phase-2 training diagnosis, (b) pivoted to Layer B, and
> (c) stood up M0 + prepared a vLLM/WSL2 spike that is gated on a REBOOT.
>
> One-line status: **env/corpus/pack/downloads/tokenizer DONE+verified (unchanged).
> Phase-2 root cause FOUND: 32B 4-bit (~18GB) exhausts the 24GB card's VRAM
> headroom -> backward allocator hangs; 14B (~9GB, ~1.5GB free) TRAINS (loss 2.18).
> The historical "contention"/"bitsandbytes stall" diagnoses were WRONG (parent-
> child process misread + TDR-as-symptom). Layer B (the harness) is the moat, not
> parameter count. M0 proposer = PROBE_MATCH (live). vLLM/WSL2 spike installed,
> REBOOT PENDING to activate WSL2 + register Ubuntu.**

---

## 0. What this program is (the WHY) — unchanged

Adapt a strong open code model to the operator's `C:\dev` ecosystem, then wrap it
in a **verified-inference harness** that beats frontier single-shot on oracle-
backed tasks, shipping every accepted answer with a re-checkable proof. Two
layers: **Layer A** = the QLoRA model (cheap, replaceable); **Layer B** = the
harness (the contribution worth publishing). **Strategic frame (new this
session): the gap is won at Layer B, not Layer A** — C2 (internal blindness)
means even the frontier can't self-certify, so a local 14B + oracle-harness beats
single-shot on verifiable tasks. The 32B VRAM wall therefore matters less than it
feels. See `HARNESS-ROADMAP.md` for the composition plan.

Authoritative docs (read in this order):
- `P: C:\dev\local-model\ROADMAP.md` — thesis, phase plan, invariants.
- `P: C:\dev\local-model\HARNESS.md` — Layer B design (loop, registry, envelope, eval).
- `P: C:\dev\local-model\HARNESS-ROADMAP.md` — **NEW**: composition spine + M0-M7 milestones + traps.
- `P: C:\dev\local-model\MEMORY-SUBSTRATE.md` — cost->~0 substrate beneath Layer B.
- `P: C:\dev\local-model\STATE.md` — live cursor (its "in flight" section is stale).

Invariants (never violate): nothing large on C: (E: is the run drive); the safety
gate is never narrowed; corpus source identifiers stay proprietary; no receipt -> no accept.

---

## 1. DONE and verified (do not redo) — env/corpus/pack/downloads unchanged

| Item | State | Evidence / Pointer |
|---|---|---|
| Run root on E: | done | `E:\local-model-run\{venv,hf-cache,data,checkpoints,logs,models,pip-cache,wheels,tmp}` |
| Python venv + stack | done, CUDA verified | `E:\local-model-run\venv\Scripts\python.exe`. py3.12.10, torch 2.6.0+cu124, transformers 5.12.1, peft 0.19.1, trl 1.7.0, accelerate 1.14.0, bitsandbytes 0.49.2 |
| Corpus + pack | done, verified | 66,158,592 tokens / 8 shards / 16,152 seqs / seq_len 4096. `E:\local-model-run\data\packed\PACK_COMPLETE.json` |
| 14B model | downloaded | 27.52 GB at `E:\local-model-run\models\Qwen2.5-Coder-14B-Instruct` |
| 32B model | downloaded, complete | 82.28 GB at `E:\local-model-run\models\Qwen2.5-Coder-32B-Instruct` |
| Tokenizer identity 14B==32B | VERIFIED | sha256(tokenizer.json) identical |
| **14B Phase-2 TRAINS** | **NEW: PROBE_MATCH** | 2-step smoke completed: `train_loss 2.18`, `train_runtime 262.4s` (~131 s/step). Log `E:\local-model-run\logs\phase2-smoke.log` (rotated variants alongside). |
| bitsandbytes 4-bit backward (isolated) | WORKS | `C:\temp\bnb_isolate.py`: 3 fwd/bwd/paged-opt steps in 0.12s, peak 0.18GB. bnb is NOT broken on this box. |
| **M0 proposer (Layer B)** | **NEW: PROBE_MATCH** | `C:\dev\local-model\harness\serve.py` — 14B base 4-bit, `/generate` + `/health`, deterministic (greedy + seeded both reproduce). Detached launcher PID was 35328 (dies on reboot; relaunch if needed). |

## 2. CORRECTED Phase-2 diagnosis (supersedes old §2)

**Old (WRONG) theories:** "GPU contention from overlapping/hung processes"
(Failure A) and "bitsandbytes nf4 backward stall on Windows" (Failure B).

**Actual root cause (confirmed by A/B): VRAM headroom.**
- 32B 4-bit (~18GB weights) on the 24.5GB card leaves ~0.2-0.4GB free -> the
  backward pass's matmul/allocator workspaces have no room -> the CUDA allocator
  spirals (creeping memory) and hangs at step 0, indefinitely.
- 14B (~9GB weights, ~1.5GB free) TRAINS (loss 2.18). The single variable that
  matters is model size -> free VRAM.
- The "two python processes = contention" was a **parent-child misread**: one
  launch presents as TWO PIDs (venv launcher parent + system-python executor
  child). There is NO watcher, NO duplicate launch, NO contention — never was.
- The full-config death's `nvlddmkm` Event 153 was **TDR firing on the hung
  kernel** — a symptom, not the cause.

**Ruled out by direct test (not theory):** GPU contention; bitsandbytes-broken
(isolates fine); seq_len (2048/1024/256 all hang on 32B); LoRA targets (all/attn);
grad-ckpt (on/off); attention impl (sdpa/eager). None move the 32B hang.

**Complications (still true):**
- Even working 14B is slow: ~131 s/step -> ~73h for a full 2-epoch run. This is
  the bitsandbytes-on-Windows penalty (Linux is ~10-40x faster). This is the
  real reason WSL2 matters for training too.
- A trivial smoke-epilogue bug (`trainer.state.to_dict()` absent in transformers
  5.12) is FIXED — now uses `ensure_trainer_state()`. Code also gained
  `--lora-targets`, `--attn`, `--no-grad-ckpt`, `--use-reentrant` flags; and
  `scripts\run_phase2.cmd` (Windows launcher, since bash isn't on PATH).

## 3. Layer B status (NEW — the strategic focus)

- `HARNESS-ROADMAP.md` persisted: composition spine (carried criterion chain,
  the §4.1 layer-composition implementation), component map, M0-M7 milestones
  each with a falsifier + promotion-ladder target, the four traps (C2 no-learned-
  accept; §4.2 composition-needs-scope; §8 wrong-attractor; §6 never-pick-
  criterion), proposer reality.
- **M0 = PROBE_MATCH.** `harness\serve.py`: 14B base 4-bit, `/generate` +
  `/health`, determinism falsifier PASSED (greedy + seeded). Proposer-agnostic
  (swap ADAPTER_PATH / MODEL_PATH). Note: ships exact result-memo, NOT
  RadixAttention prefix caching (that is M5 / the WSL spike).
- **M1 UNBLOCKED** (minimal witnessed loop: index retrieve -> M0 propose ->
  pytest oracle in sandbox -> proof envelope -> crucible witness -> MATCH/DRIFT/
  UNVERIFIABLE). Not yet built.

## 4. vLLM/WSL2 spike (NEW — REBOOT PENDING)

De-risks M5 (real prefix caching) AND the training-speed question (fast
bitsandbytes on Linux). Pre-flight (Win11 build 26220, driver 610.62, Hypervisor
present, E: accessible) all PASS. `wsl --install -d Ubuntu --no-launch` returned
rc=0 with: **"Changes will not be effective until the system is rebooted."**

- Scripts ready: `harness\wsl_vllm_spike.sh` (runs in WSL2: preflight -> venv ->
  `pip install vllm` -> serve 14B 4-bit with `--enable-prefix-caching` -> probe
  determinism + prefix-cache hit) and `harness\wsl_vllm_run.cmd` (Windows launcher).
- The spike runs as root inside WSL (no user-setup/sudo needed).

## 5. Resume procedure (after the reboot)

```
# 0. After reboot, in a new opencode session in C:\dev\local-model:
# 1. Confirm WSL2 + Ubuntu registered + GPU visible:
#      wsl -l -v                       # expect Ubuntu
#      wsl nvidia-smi                  # expect the 4090
# 2. Drive the spike (this session does it for you once you say "continue"):
#      wsl bash /mnt/c/dev/local-model/harness/wsl_vllm_spike.sh
#    (first run: ~5-15 min vllm install + ~10-15 min slow drvfs model load)
# 3a. If spike PASSES (determinism + prefix-cache hit) -> vLLM is the proposer;
#     M0 (transformers server) retired; proceed to M1 against the vLLM endpoint.
# 3b. If spike FAILS -> relaunch M0 fallback:
#     WMI-launch: cmd /c ""E:\local-model-run\venv\Scripts\python.exe" -u
#                  "C:\dev\local-model\harness\serve.py" >> serve.log 2>&1"
# 4. Build M1 (the minimal witnessed loop). See HARNESS-ROADMAP.md M1.
```

## 6. Strategic frame (read before any "just get the 32B training working" urge)

The moat is Layer B. Investing in harness composition (oracle adapters, carried-
criterion envelope, independent-perspective reconcile, receipt cache) widens the
frontier gap more than squeezing the 32B onto 24GB. The 14B + harness is the
pragmatic near-term proposer; the 32B is aspirational and needs WSL2 (fast
bitsandbytes) or a bigger GPU to be practical. **Pursue Layer B first; let the
WSL spike (which also unlocks fast training) resolve the 32B question.**

## 7. Parked / lower priority

- **32B CPU-offload experiment**: build_model was READ but the offload edit was
  NOT applied. With 32GB RAM / 24.8 free, offload is marginal AND slow. Lower
  priority than Layer B; revisit only if WSL2 training also can't fit the 32B.
- **Ambiguous checkpoints** were renamed to `*.stale-20260704-0015` (do NOT
  resume from them; start fresh).
- **Data discrepancy** (non-blocking): `safety_report.txt` says 0 dropped vs
  `manifest_summary.json` 33 gated. Re-verify the safety gate before any corpus
  expansion; it must always fail CLOSED.

## 8. Forensic pointers (re-derive any claim)
- 14B trains: `E:\local-model-run\logs\phase2-smoke.log` (train_loss 2.18).
- bitsandbytes isolates fine: `C:\temp\bnb_isolate.py`.
- 32B VRAM hang: any 32B smoke log in `E:\local-model-run\logs\phase2-smoke*.log`.
- Parent-child process pair (the "contention" misread): captured via WMI tracer.
- nvlddmkm Event 153 (TDR-as-symptom): Windows System log around the 32B deaths.
- M0 determinism: harness/serve.py two-call prefix test (passed).
