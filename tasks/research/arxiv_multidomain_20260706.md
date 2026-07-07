# Multi-domain arXiv sweep (2026-07-06) — receipt-sealed

> "Scan all domains" pass, via `gather_arxiv` (each row carries a sha256; each
> query a sealed digest). 15 domains total across two rounds (the 8 harness-lane
> queries in `arxiv_sweep_20260706.json` + the 7 broad-domain queries below).
> Standouts are the CURRENT (2026) papers that touch the harness thesis.

## Round 2 — broad domains (7 sealed queries)

| Domain | Notable / current papers | Seal (prefix) |
|---|---|---|
| program synthesis / SAT-SMT / repair | Survey of AI program-repair & codegen (2411.07586); Model+Program Repair via SAT (0710.3332); Smt-Switch solver-agnostic API (2007.01374) | 2b74de37 |
| reproducibility / provenance | Provenance + data-differencing for workflow reproducibility (1406.0905); Cloud provenance to reproduce workflow execution (1803.06867); reproducible artifacts via Docker (2308.14122) | 97706ea0 |
| quality-diversity / open-ended | QD benefits without explicit diversity maintenance? (2305.07767); MAP-Elites open-ended env+agent search (2305.01153); QD Through Surprise (1807.02397) — validates our AWG/MAP-Elites lane | 1cf57aa9 |
| LLM reasoning / process reward | **ProcessThinker: rollout-based PROCESS reward (2606.11209, 2026)** — per-step verification = our transitive-witness per-node re-check; Long-CoT survey (2503.09567); DiffCoT (2601.03559, 2026) | 1ff3ac22 |
| formal verification / Rust / seL4 | **KVerus: scalable formal-verification proof-gen for Rust (2605.03822, 2026)**; **Neuro-Symbolic Proof Generation for Systems Software Verification (2603.19715, 2026)**; RustCompCert verified compiler (2602.07455, 2026); seL4 driver verification (2311.03585) | 62e80691 |
| neural rendering / procedural | 3D Gaussian Splatting (2308.04079); NeRF review post-splatting (2210.00379); Gaussian Wave Splatting for holography (2505.06582) — the creative/render lane | 73a1b89a |
| distributed / low-comm training | **DiLoCo (2311.08105)** + **Factored Gossip DiLoCo (2606.22768, 2026)** — decentralized LLM training = the democratization lane (our 32B-on-a-4090 result) | 8545b119 |

## The cross-cut that matters (honest)

The field-wide signal reinforces the 2026-07-06 novelty audit: **process-level
verification is now mainstream** (ProcessThinker rollout process reward; the
Trust-but-Verify survey). Our transitive-witness folds per-node (process-level)
re-checks over a citation cone — the *composition* is still the differentiator,
not the per-node check. And **neuro-symbolic PROOF GENERATION for real systems
code** (KVerus, 2603.19715) is exactly the "verified-inference on a hard oracle
domain" our M7 thesis predicts — a concrete future oracle class (Verus/Lean) to
plug into the registry. Distributed low-comm training (DiLoCo family) is the
scale path beneath the 32B-on-commodity-HW democratization result.

Full receipts (sha256 per paper) are in the session gather digests; this file is
the human index. No claims are made from titles alone — deep-read before adopting.
