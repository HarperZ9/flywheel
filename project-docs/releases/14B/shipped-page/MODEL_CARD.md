# Flywheel-Local-Coder-14B Model Card

A verified, retraceable continued-pretraining build on Qwen2.5-Coder-14B-Instruct.
Identity and provenance are complete and re-checkable; benchmark evidence is
attached, and no capability uplift over the base model is claimed.

## Model identity

- Release name: `Flywheel-Local-Coder-14B`
- Model file: `telos-coder-14b-cpt2020-q4_k_m.gguf`
- Base model: `Qwen2.5-Coder-14B-Instruct` (Alibaba Cloud / Qwen team, Apache-2.0)
- Adapter: `checkpoint-2020`, QLoRA continued pretraining, 2020 steps over 2 epochs
- Training loss: final logged 0.444, minimum 0.359, mean 0.492 across 202 logged points
  (corrected 2026-07-26, see [CORRECTIONS.md](CORRECTIONS.md))
- Composition: base weights merged with the adapter, then quantized
- Quantization: Q4_K_M (GGUF)
- Size: 8.99 GB (8,988,110,880 bytes)
- Model SHA-256: `613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be`
- Adapter (safetensors) SHA-256: `4de07c6ea342d1cc200d4a6e2b28a63f6ee37f34c5c0926c35d8c7db74d38d0f`
- LoRA GGUF SHA-256: `c89091709d7f385226000091dca976b7ce68086255e78af96599d06b6b52f547`
- Local serving name: Ollama `flywheel-local-coder-14b`

The full chain is recorded in [provenance.json](provenance.json) and tied to the
downloaded bytes by [checksums.sha256](checksums.sha256).

## Training data

Continued pretraining on a 66.2-million-token corpus of 17,997 files from a real,
working development ecosystem: production code, tests, documentation, and
research notes. Corpus content hash
`68345cdc6667f20d1678ac0a9139edc170348dfdebb9ae6045cde3d204f4fe62`; pack shards
hash `018798dfce7d4c86f5a6ea502a383553220f2e76facfe76acbe52b1c278ae543`. Corpus
source identifiers stay proprietary.

## Intended use

Local-first coding: completion, small functions, refactors, test writing, and
tool-calling on your own hardware, served via Ollama or llama.cpp. It pairs
naturally with a propose-then-verify loop, which is how it is benchmarked.

## Limitations

- Q4_K_M quantization; quantization loss relative to the merged fp16 weights is
  not measured.
- No capability uplift over the base model is claimed; our own measurement of
  that difference includes zero. See [BENCHMARKS.md](BENCHMARKS.md).
- Refusal behavior, bias, and content boundaries are inherited from the base
  model and are not separately audited here.

## License

Apache-2.0 derivative. Base model `Qwen2.5-Coder-14B-Instruct` is Copyright
Alibaba Cloud, Apache-2.0. This artifact merges a locally trained QLoRA adapter
into those weights and retains the Apache-2.0 license with attribution.

## Benchmark status

Evidence attached. On the internal evaluation sets the model passes 8 of 8
baseline tasks and 8 of 10 deliberately contract-heavy hard tasks in a single
attempt, each number with a confidence interval and the JSON to re-run it. See
[BENCHMARKS.md](BENCHMARKS.md) and the `benchmarks/` folder.
