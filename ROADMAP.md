# local-model — verified-inference frontier-output program

> Durable program backbone. This file is the source of truth across sessions.
> If context is lost, read this first, then `STATE.md` for the live cursor.

## The thesis

Frontier **weights** are not reachable on 24 GB of VRAM. Frontier **output**
on verifiable tasks is. The gap is closed at inference time, not in the weights:
a strong local model proposes, real verifiers dispose, retrieval carries the
knowledge, and every accepted answer arrives with a re-checkable proof. On any
task that has an oracle (code that compiles and passes tests, a proof that
type-checks, a number that checks out) a system doing a lot of *verified*
inference can match or beat a frontier model's single shot. That is the whole
program, and it is the operator's reconcile loop (perceive, check against an
unauthored criterion, carry re-checkable proof) applied to test-time compute.

The model is the cheap, replaceable part. The verified-inference harness around
it is the research contribution and the thing worth publishing.

## Two layers

**Layer A — the specialized model (the cheap part).**
Adapt a strong open **code** base to the operator's `C:/dev` ecosystem so it
speaks the actual codebases, idioms, and APIs. At 52.8M tokens this is
continued domain-adaptation plus instruction tuning, not from-scratch
pretraining. LoRA / QLoRA on the 4090.

**Layer B — the verified-inference harness (the contribution).**
Test-time search where the model generates candidates and REAL verifiers score
them. Retrieval carries knowledge the weights do not hold. The operator's own
flagships are the organs, already built:
- **crucible** — verifier / judgment organ (register, steelman, measure, refine, witness MATCH/DRIFT/UNVERIFIABLE).
- **index** — code retrieval, symbol graph, context envelopes over the ecosystem.
- **gather** — external knowledge retrieval with source receipts.
- **forum** — multi-agent orchestration with a witnessed causal ledger.
- **telos** — `model_foundry`, `learning_forge`, `measurement_layers`, `proof`.

The claim to prove: `verified-inference-system(local model) > single-shot(frontier)`
on oracle-backed tasks, with receipts.

## Hardware reality (measured 2026-07-03)

- GPU: RTX 4090, 24 GB VRAM (~22 GB free at idle).
- Drives: **C: only ~105 GB free (near full)**, **E: ~859 GB free**, D: 461 GB, H: 331 GB.
- **Rule: nothing large touches C:.** All weights, caches, tokenized shards,
  checkpoints, and logs live on E:.
- Run root: `E:\local-model-run\` = `{ venv, hf-cache, data, checkpoints, logs, models, pip-cache }`.
- Env for every training/inference process:
  `HF_HOME=E:\local-model-run\hf-cache`, `PIP_CACHE_DIR=E:\local-model-run\pip-cache`.
- Python 3.12.10. Stack: torch (cu124), transformers, peft, trl, accelerate,
  datasets, bitsandbytes, safetensors, sentencepiece.

## The corpus (operator-curated, source identifiers proprietary)

- Authoritative allowlist: `dataset/allowlist.yaml` (hand-set by the operator).
- Manifest built by `dataset/corpus_manifest.py` (safety gate baked in, cannot
  be disabled by editing an allowlist).
- Size: **17,997 files, 211.3 MB, ~52.8M tokens** (est).
- Mix: Markdown, JSON, Python, Rust, C/C++, JS/MJS, YAML/TOML, some HTML/JSONL.
  Code-dominant, which fits a code-first base.
- **Safety gate: 33 opsec / dual-use paths dropped and logged** in
  `dataset/safety_report.txt`. Never train a weaponizable artifact. Non-negotiable.

## Phase plan

- **Phase 0 — env + data. (in progress)**
  E: run root scaffolded; training stack installing into `E:\...\venv`; manifest
  regenerated from `allowlist.yaml`; safety gate verified (33 drops logged).
- **Phase 1 — base model + tokenize/pack.**
  Download base to `E:\...\models`; tokenize + pack the manifest into training
  shards on E:. Deterministic and re-runnable. Base choice = operator checkpoint
  (default below).
- **Phase 2 — domain adaptation (QLoRA CPT).**
  LoRA continued-pretraining on the corpus. Checkpoint to E:, resumable, logged.
  This is the upkeep the assistant runs to completion.
- **Phase 3 — instruction / SFT layer.**
  Build oracle-friendly pairs FROM the ecosystem (docstring→impl, test→impl,
  signature→body, commit message→diff). Fine-tune on top of Phase 2.
- **Phase 4 — verified-inference harness (Layer B).**
  Generate→verify loop. Verifiers: python test runner, rust `cargo test`/compile,
  Lean/proof checker, crucible witness. Retrieval: index + gather. Search:
  best-of-N → beam → verifier-guided (MCTS-lite) over the oracle reward.
- **Phase 5 — eval + write-up.**
  Oracle-backed benchmark. System vs single-shot frontier, with witnessed
  receipts. This is the publishable result.

Open-ended reasoning (the second focus) generalizes Layer B: any task with a
checkable oracle (Lean for proofs, numeric checks for math, self-play /
simulation verifiers for strategy) rides the same harness. The biology /
experimentation models are a parallel specialized track that reuses Layer B
with domain verifiers.

## Operator decision checkpoints

1. **Base model (Phase 1). SELECTED: `Qwen2.5-Coder-32B-Instruct`** (operator
   choice, 2026-07-03). ~62 GB bf16 download; ~18 GB in 4-bit → aggressive but
   viable QLoRA on 24 GB at seq_len 2048, r=16, paged 8-bit optim, grad
   checkpointing. Chosen for maximum base capability in the verified-inference
   proposer. 14B-Instruct kept as a secondary asset (fast harness prototyping /
   ensemble / speculative-draft). Tokenizer is identical across the
   Qwen2.5-Coder family, so the packed shards are reusable within it (verify
   tokenizer.json sha256 match before training).
2. **License / publish posture.** Matches the operator's fair-source flagship stance.

## Invariants

- Nothing large on C:. E: is the run drive.
- The safety gate is never disabled or narrowed. Dual-use content never trains.
- Corpus source identifiers stay proprietary; only aggregate stats leave this repo.
- Every accepted inference-time answer carries a re-checkable proof. No receipt, no accept.
