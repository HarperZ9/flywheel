# Flywheel-Local-Coder-32B Model Card

Status: trained artifact verified, staged for operator-gated upload. Identity and the full provenance chain are re-checkable; benchmark evidence is pending.

## Model identity

- Release name: `Flywheel-Local-Coder-32B`
- Artifact file: `telos-coder-32b-cpt2019-q4_k_m.gguf`
- Base model: `Qwen2.5-Coder-32B-Instruct` (Alibaba Cloud / Qwen team, Apache-2.0)
- Adapter: `checkpoint-2019`, QLoRA continued pretraining (r 16, alpha 32, dropout 0.05), 2019 steps, epoch 0.25, final logged train loss ~0.768
- Composition: base weights merged with the adapter, then quantized
- Quantization: Q4_K_M (GGUF)
- Size: 19,851,336,480 bytes
- Artifact SHA-256: `65e6133fbe4d12579a776047a71bebb98ab86f9e3d343ed821b51dac0ce312f4`
- Merged fp16 GGUF (local build intermediate, not published): `telos-coder-32b-merged-f16.gguf`, SHA-256 `3360f7db86b8493dd444c4b03e113d61be6c06084ddb91c8557847f58036a3ee`
- Adapter (safetensors) SHA-256: `d2ff1d3042c9b015d8d01b6e195cf95acedc133bf4efe78692e4349a3608e286`
- LoRA GGUF SHA-256: `08e7d21cfde1af768c877ecc18ee6343c87711c0c38b8c5b16feb9890f94cbac`
- Artifact location: `E:\local-model-run\gguf-work-32b\telos-coder-32b-cpt2019-q4_k_m.gguf`
- Local serving name: Ollama `flywheel-local-coder-32b`
- Manifest: `C:\dev\local-model\tasks\research\gguf_ship_manifest_checkpoint2019_32b.json` (schema `telos.model-artifact/v1`)

## Training data

Continued pretraining on the operator's `C:\dev` ecosystem corpus, the same packed corpus that trained the 14B track: 66,158,592 tokens, 8 shards, 16,152 sequences, seq_len 4096, from 17,997 corpus files (`E:\local-model-run\data\packed\PACK_COMPLETE.json`). Qwen2.5-Coder 14B and 32B share a tokenizer, so one packed corpus trains both. Corpus content hash `68345cdc6667f20d1678ac0a9139edc170348dfdebb9ae6045cde3d204f4fe62`; pack shards hash `018798dfce7d4c86f5a6ea502a383553220f2e76facfe76acbe52b1c278ae543`. Corpus source identifiers stay proprietary.

## Intended use

Local-first agentic coding inside the flywheel harness, served via Ollama or llama.cpp. The 32B trades size for capacity over the 14B; both are reached through the same harness endpoint contract.

## Limitations

- Q4_K_M quantization; quantization loss relative to the merged fp16 weights is not measured.
- Trained for a quarter epoch (2019 steps) of continued pretraining; a light domain adaptation, not a full retrain.
- Built and tested for local serving (Ollama, llama.cpp).
- No benchmark evidence exists yet. Benchmarks are pending. No capability uplift over the base model is claimed.
- Deterministic smoke (ollama `/api/generate`, temp 0, seed 7, num_predict 64, byte-identical reruns, MATCH, generation hash prefix `403b2e8b21df9f55`) is the only behavioral evidence recorded.

## License

Apache-2.0 derivative. Base model `Qwen2.5-Coder-32B-Instruct` is Copyright Alibaba Cloud, Apache-2.0. This artifact merges a locally trained QLoRA adapter into those weights and retains the Apache-2.0 license with attribution. The base weights are never republished on their own; only the adapter and the merged quantization are released.

## Current benchmark status

Benchmarks are pending. No benchmark result is recorded for this artifact.
