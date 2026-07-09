# Flywheel-Local-Coder-14B Safety and Accountability Notes

Status: draft. Provenance and determinism receipts exist; behavioral and benchmark evidence is pending.

## Accountability posture

This release makes no capability claims. It states what the artifact is, how it was built, and which receipts back each statement. Anything without a receipt is labeled pending.

## Receipts that exist

- Provenance chain (`C:\dev\local-model\tasks\research\gguf_ship_manifest_checkpoint2020.json`, schema `telos.model-artifact/v1`), each layer re-derivable:
  corpus_content_hash `68345cdc6667f20d1678ac0a9139edc170348dfdebb9ae6045cde3d204f4fe62` -> pack_shards_hash `018798dfce7d4c86f5a6ea502a383553220f2e76facfe76acbe52b1c278ae543` -> checkpoint_adapter_sha256 `4de07c6ea342d1cc200d4a6e2b28a63f6ee37f34c5c0926c35d8c7db74d38d0f` -> GGUF sha256 `613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be`.
- Deterministic smoke: llama-completion, temp 0, seed 7, n 48; reruns byte-identical (MATCH); output sha256 `970af540244384407918aa3b0172b403c24d17800e3c514c3c19937d88c7e636`.

## Receipts required before publication

- Endpoint gate artifacts (`harness.model-endpoint-gate/v1`) with generation_ok for this model.
- Benchmark evidence artifacts attached to the release row. Benchmarks are pending; no benchmark result exists yet.
- Receipt-backed limitations and known failure modes.
- Refusal/friction behavior, if measured.
- Secret-handling boundary check on all shipped examples.

## Capability claims

None. No uplift over the base `Qwen2.5-Coder-14B-Instruct` is claimed. Any comparison against the base model must come from executed benchmark artifacts, which do not exist yet.
