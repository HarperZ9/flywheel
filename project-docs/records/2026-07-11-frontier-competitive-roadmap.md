# Frontier competitive roadmap (2026-07-11)

Distilled from a six-axis web-grounded research sweep (routing, verification,
agentic-harness landscape, context/memory, provenance, evaluation). Citations
marked **[real]** are pre-2026 and independently known; **[swept]** were fetched
and marked verified by the research agents on 2026-07-11 but not re-checked here,
so treat their exact IDs as moderate-confidence until reconfirmed.

## The wedge

Three axes converged on one thing: a visible-test-only accept gate is **gameable**,
and the 2025-2026 fix is oracle/trajectory **integrity against reward-hacking**.
This is the purest expression of Flywheel's own thesis (a check that can fail AND
cannot be tricked into passing), and no competitor ships it. It is the durable
differentiator to lead with.

Discipline that makes the receipts mean something (both correctly REJECTED by the
sweep as thesis-breaking): do NOT add an **LLM-as-judge accept gate** (learned
model on the accept path, what most incumbents ship), and do NOT adopt **KV-cache
benchmark encoding** for the hard lane (learned-model dependency on task admission).

## Ranked wins (all zero-dep, no learned model on the accept path)

| # | Win | Effort | Status | Grounding |
|---|---|---|---|---|
| 1 | **Reward-hacking integrity guard** (refuse a tampered pass; ledger trajectory flags) | S-M | **SHIPPED 2026-07-11** `harness/integrity.py` | RLVR reward-hacking; SpecBench [swept] |
| 2 | Non-learned verifier ensembling (consensus over test + property + metamorphic) | M | **SHIPPED 2026-07-11** `harness/consensus.py` (ConsensusOracle + RepeatConsistencyOracle) | Weaver / FUSE / BoN-MAV [swept] |
| 3 | Sample-agreement escalation gate (k-sample agreement before escalating) | S | next | Semantic Agreement, EMNLP 2025, 2509.21837 [swept] |
| 4 | Held-out / adversarial oracle tier (accept needs a check the model never saw) | M | next | SpecBench [swept]; UTBoost weak-test finding [swept] |
| 5 | Constraint-pinning in compaction (never fold gate/policy text away) | S | next (needs verify_compaction rework) | Governance-Decay [swept] |
| 6 | Deterministic LexRank compaction fallback (replace "first line, truncated") | S | **SHIPPED 2026-07-11** `harness/compaction.py` (default fold) | LexRank, 1109.2128 [real] |
| 7 | in-toto/DSSE receipt shape + full-length hashes (drop 64-bit truncation) | S | **SHIPPED 2026-07-11** `harness/envelope.py` (to_in_toto_statement / to_dsse_envelope / content_sha256) | SLSA / in-toto / Sigstore / C2PA [real] |
| 8 | Zero-dep MCP client so /api/agent calls OUT to the MCP ecosystem | M | | MCP now table-stakes across all incumbents |
| 9 | Cost/success-rate-ordered failover chain (stdlib frequency-table bandit) | M | | Cascade Routing, 2410.10347 [swept] |
| 10 | Curated ~100-task hard lane + contamination freshness gate | S-M | | Terminal-Bench 2.0, LiveCodeBench, SWE-bench-Live [swept]; SWE-bench Verified now deprecated for eval |
| 11 | Merkle-tree world root with inclusion/consistency proofs | M | | RFC 9162 [real] |
| 12 | Content-addressed fold index for exact-text recall (mem0-class, no vectors) | M | | Context-Folding, 2510.11967 [swept] |

## Key sources by axis

- **Routing/cascades:** RouteLLM 2406.18665 [real]; FrugalGPT 2305.05176 [real];
  Hybrid LLM 2404.14618 [real]; RouterBench 2403.12031 [real, eval dataset];
  Cascade Routing 2410.10347, BEST-Route (github microsoft/best-route-llm),
  UniRoute 2502.08773, Semantic Agreement 2509.21837 [swept].
- **Verification:** Weaver / FUSE / BoN-MAV verifier-ensembling; conformal risk
  control for calibrated escalation; oracle-free dual-execution agreement (CodeT /
  Agentic PBT) [swept].
- **Harness landscape:** MCP ecosystem (client gap); sub-agent fan-out; ACP/AGENTS.md
  convention; OS-level sandboxing (Codex Seatbelt/bubblewrap, OpenHands Docker) [swept].
- **Context/memory:** LexRank 1109.2128 [real]; Context-Folding 2510.11967;
  KVFlow 2507.07400 (prefix stability); Governance-Decay; mem0/MemoryOS [swept].
- **Provenance:** in-toto ITE-6, DSSE, SLSA, Sigstore/cosign, C2PA, CycloneDX
  ML-BOM, RFC 9162 transparency logs [real].
- **Evaluation/data:** SWE-bench / SWE-bench Verified (now deprecated for eval),
  LiveCodeBench, BigCodeBench, EvalPlus, SWE-bench-Live, Terminal-Bench 2.0,
  SWE-smith (private task minting), UTBoost (leaked-test finding) [swept/real mix].

Full raw findings (157 KB JSON) were produced by workflow `wf_025849af-766`.
