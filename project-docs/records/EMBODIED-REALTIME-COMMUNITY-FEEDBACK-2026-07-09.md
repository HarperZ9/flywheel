# Embodied realtime community feedback benchmark note - 2026-07-09

Status: planned, not executed.

## Mechanism

The Boris / ENBSeries feedback is now represented as benchmark pressure rather than as model truth. The harness should score realtime local-model usefulness across sensor grounding, procedural spatial repair, small-model efficiency, control-boundary discipline, affective stability, receipt quality, and model-card groundedness.

## Verified from current operator relay

- The feedback asks what "AI real-time senses" means for robotics-style systems.
- The feedback asks whether very small models can trade broad intelligence for realtime robotics usefulness.
- The feedback describes code-drawn visual reasoning and repair behavior as an experiment target.
- The feedback raises simplified multimodal projection as a useful architecture to test.
- The feedback identifies possessive, jealous, humiliating, or dominance-oriented companion behavior as a failure mode worth measuring.

## Not verified yet

- The identity and availability of every named model lead.
- The quoted modality, context-length, uncensored, distillation, or license claims.
- Whether any named model is appropriate for publication-facing comparisons.

## Benchmark changes

- `embodied-realtime-multimodal-v1.json` now includes weighted score dimensions.
- The benchmark contract now includes eight explicit probe cases derived from the feedback.
- Run reports must include parameter class, quantization, provider role, harness name, probe ID, latency, memory, score breakdown, failure class, model-card claim status, and artifact paths.
- `agentic-task-set-v1.json` now includes a focused model-card claim-grounding task before result claims.
- `scripts/run_model_card_claim_table.py` can generate a non-executing claim table that keeps relayed model leads separate from sourced model-card facts.

## Next executable step

Generate the non-executing agentic task manifest and model-card claim table, then run targeted validation only after operator approval.
