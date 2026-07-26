# Flywheel-Local-Coder-32B Model Card

A verified, retraceable continued-pretraining build on Qwen2.5-Coder-32B-Instruct.
Identity and provenance are complete and re-checkable; benchmark evidence is
pending and no capability uplift is claimed.

## Model identity

- Release name: `Flywheel-Local-Coder-32B`
- Model file: `telos-coder-32b-cpt2019-q4_k_m.gguf`
- Base model: `Qwen2.5-Coder-32B-Instruct` (Alibaba Cloud / Qwen team, Apache-2.0)
- Adapter: `checkpoint-2019`, QLoRA continued pretraining (r 16, alpha 32,
  dropout 0.05), 2019 steps (a quarter epoch)
- Composition: base weights merged with the adapter, then quantized
- Quantization: Q4_K_M (GGUF)
- Size: 18.5 GB (19,851,336,480 bytes)
- Model SHA-256: `65e6133fbe4d12579a776047a71bebb98ab86f9e3d343ed821b51dac0ce312f4`
- Adapter (safetensors) SHA-256: `d2ff1d3042c9b015d8d01b6e195cf95acedc133bf4efe78692e4349a3608e286`
- LoRA GGUF SHA-256: `08e7d21cfde1af768c877ecc18ee6343c87711c0c38b8c5b16feb9890f94cbac`
- Local serving name: Ollama `flywheel-local-coder-32b`

The full chain is recorded in [provenance.json](provenance.json) and tied to the
downloaded bytes by [checksums.sha256](checksums.sha256).

## Training data

Continued pretraining on a 66.2-million-token corpus of 17,997 files from a real,
working development ecosystem: production code, tests, documentation, and
research notes. This is the same packed corpus used for the 14B (Qwen2.5-Coder
14B and 32B share a tokenizer). Corpus content hash
`68345cdc6667f20d1678ac0a9139edc170348dfdebb9ae6045cde3d204f4fe62`; pack shards
hash `018798dfce7d4c86f5a6ea502a383553220f2e76facfe76acbe52b1c278ae543`. Corpus
source identifiers stay proprietary.

## Intended use

Local-first coding: completion, functions, refactors, test writing, and
tool-calling on your own hardware, served via Ollama or llama.cpp. It pairs
naturally with a propose-then-verify loop.

## Limitations

- Q4_K_M quantization; quantization loss relative to the merged fp16 weights is
  not measured.
- A quarter-epoch (2019-step) continued-pretraining adaptation, a light domain
  pass, not a full retrain.
- No benchmark evidence exists yet. No capability uplift over the base model is
  claimed. A deterministic generation smoke (temp 0, seed 7, byte-identical
  reruns, MATCH) is the only behavioral evidence recorded.
- Refusal behavior, bias, and content boundaries are inherited from the base
  model and are not separately audited here.

## License

Apache-2.0 derivative. Base model `Qwen2.5-Coder-32B-Instruct` is Copyright
Alibaba Cloud, Apache-2.0. This artifact merges a locally trained QLoRA adapter
into those weights and retains the Apache-2.0 license with attribution. The base
weights are never republished on their own; only the merged quantization and the
adapter are released.

## Benchmark status

Pending. No benchmark result is recorded for this model. See
[BENCHMARKS.md](BENCHMARKS.md).
