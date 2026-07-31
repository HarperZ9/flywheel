# Flywheel-Local-Coder-32B Safety and Accountability Notes

Status: provenance and determinism receipts exist and are re-checkable; behavioral and benchmark evidence is pending.

## Accountability posture

This release makes no capability claims. It states what the artifact is, how it was built, and which receipts back each statement. Anything without a receipt is labeled pending.

## Receipts that exist

- Provenance chain (`tasks/research/gguf_ship_manifest_checkpoint2019_32b.json`, schema `telos.model-artifact/v1`), each layer re-derivable:
  corpus_content_hash `68345cdc6667f20d1678ac0a9139edc170348dfdebb9ae6045cde3d204f4fe62` -> pack_shards_hash `018798dfce7d4c86f5a6ea502a383553220f2e76facfe76acbe52b1c278ae543` -> checkpoint_adapter_sha256 `d2ff1d3042c9b015d8d01b6e195cf95acedc133bf4efe78692e4349a3608e286` -> LoRA GGUF `08e7d21cfde1af768c877ecc18ee6343c87711c0c38b8c5b16feb9890f94cbac` -> merged Q4_K_M GGUF `65e6133fbe4d12579a776047a71bebb98ab86f9e3d343ed821b51dac0ce312f4` (re-verified by re-hash).
- Deterministic smoke: ollama `/api/generate`, temp 0, seed 7, num_predict 64; reruns byte-identical (MATCH); generation hash prefix `403b2e8b21df9f55`.

## Receipts required before capability claims

- Endpoint gate artifacts (`harness.model-endpoint-gate/v1`) with generation_ok for this model.
- Benchmark evidence artifacts attached to the release row. Benchmarks are pending; no benchmark result exists yet.
- Receipt-backed limitations and known failure modes.
- Secret-handling boundary check on all shipped examples.

## Capability claims

None. No uplift over the base `Qwen2.5-Coder-32B-Instruct` is claimed. Any comparison against the base model must come from executed benchmark artifacts, which do not exist yet. The base weights are never republished on their own.
