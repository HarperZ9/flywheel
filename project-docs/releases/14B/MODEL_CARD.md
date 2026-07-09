# Flywheel-Local-Coder-14B Model Card

Status: draft, not publish-ready. Identity and provenance are verified; benchmark evidence is pending.

## Model identity

- Release name: `Flywheel-Local-Coder-14B`
- Artifact file: `telos-coder-14b-cpt2020-q4_k_m.gguf`
- Base model: `Qwen2.5-Coder-14B-Instruct` (Alibaba Cloud / Qwen team, Apache-2.0)
- Adapter: `checkpoint-2020`, QLoRA continued pretraining, train_loss 0.035
- Composition: base weights merged with the adapter, then quantized
- Quantization: Q4_K_M (GGUF)
- Size: 8,988,110,880 bytes
- Artifact SHA-256: `613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be`
- Adapter SHA-256: `4de07c6ea342d1cc200d4a6e2b28a63f6ee37f34c5c0926c35d8c7db74d38d0f`
- LoRA GGUF SHA-256: `c89091709d7f385226000091dca976b7ce68086255e78af96599d06b6b52f547`
- Artifact location: `E:\local-model-run\release\flywheel-local-coder-14b\telos-coder-14b-cpt2020-q4_k_m.gguf`
- Local serving name: Ollama `flywheel-local-coder-14b`
- Manifest: `C:\dev\local-model\tasks\research\gguf_ship_manifest_checkpoint2020.json` (schema `telos.model-artifact/v1`)

## Training data

Continued pretraining on the operator's `C:\dev` ecosystem corpus. Pack numbers (verified in `HANDOFF.md` and `E:\local-model-run\data\packed\PACK_COMPLETE.json`): 66,158,592 tokens, 8 shards, 16,152 sequences, seq_len 4096, from 17,997 corpus files. Corpus content hash `68345cdc6667f20d1678ac0a9139edc170348dfdebb9ae6045cde3d204f4fe62`; pack shards hash `018798dfce7d4c86f5a6ea502a383553220f2e76facfe76acbe52b1c278ae543`. Dataset receipt: `tasks/research/dataset_receipt_checkpoint2020.json`. Corpus source identifiers stay proprietary.

## Intended use

Local-first agentic coding inside the flywheel harness, served via Ollama or llama.cpp on the operator's Windows machine. Receipts, endpoint gates, and benchmark evidence are required before any wider publication.

## Limitations

- Q4_K_M quantization; quantization loss relative to the merged fp16 weights is not measured.
- Built and tested for Windows local serving only.
- No benchmark evidence exists yet. Benchmarks are pending. No capability uplift over the base model is claimed.
- Deterministic smoke (llama-completion, temp 0, seed 7, byte-identical reruns, MATCH) is the only behavioral evidence recorded.

## License

Apache-2.0 derivative. Base model `Qwen2.5-Coder-14B-Instruct` is Copyright Alibaba Cloud, Apache-2.0. This artifact merges a locally trained QLoRA adapter into those weights and retains the Apache-2.0 license with attribution. See the LICENSE file shipped next to the artifact.

## Current benchmark status

Benchmarks are pending. No benchmark result is recorded for this artifact.

## Current publication verdict

Do not publish. Blocked on benchmark evidence, endpoint gate history, and explicit operator approval.
