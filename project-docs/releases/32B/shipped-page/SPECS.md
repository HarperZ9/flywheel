# Spec Sheet

## The model

| | |
|---|---|
| Name | Flywheel-Local-Coder-32B |
| Architecture | qwen2 (transformer, decoder-only) |
| Parameters | 32.5B |
| Context length | 32,768 tokens |
| Capabilities | chat, code completion, tool calling |
| Base model | Qwen/Qwen2.5-Coder-32B-Instruct |
| License | Apache-2.0 with Qwen attribution |

## The files

| | |
|---|---|
| Model | `telos-coder-32b-cpt2019-q4_k_m.gguf`, GGUF single file |
| Quantization | Q4_K_M |
| Size | 18.5 GB (19,851,336,480 bytes) |
| SHA-256 | `65e6133fbe4d12579a776047a71bebb98ab86f9e3d343ed821b51dac0ce312f4` |
| Adapter | `telos-coder-32b-cpt2019-lora.gguf`, LoRA GGUF, 268 MB |
| Adapter SHA-256 | `08e7d21cfde1af768c877ecc18ee6343c87711c0c38b8c5b16feb9890f94cbac` |
| Verify | `sha256sum telos-coder-32b-cpt2019-q4_k_m.gguf` and compare with [checksums.sha256](checksums.sha256) |

## Hardware guidance

- **GPU**: the Q4_K_M weights are ~18.5 GB. A 24 GB card holds the weights but
  leaves little headroom for a long context; expect to offload some layers to
  CPU as context grows. Cards below 24 GB run with partial CPU offload and lower
  speed.
- **CPU only**: works, but this is a 32B model. Budget roughly 20 GB of free RAM
  for weights plus context. Generation is noticeably slower than the 14B; usable
  for chat and completion when you are not latency-sensitive.
- **Disk**: 18.5 GB for the model file, plus 268 MB if you also pull the adapter.

Runs anywhere llama.cpp or Ollama runs: Windows, Linux, macOS. If you want the
same behavior at lower memory and higher speed, the 14B sibling is the lighter
option.

## How it was trained

Continued pretraining (QLoRA) of the base model on a 66.2-million-token corpus
of 17,997 files from a real, working development ecosystem: production code,
tests, documentation, and research notes. This is the same packed corpus used
for the 14B; Qwen2.5-Coder 14B and 32B share a tokenizer, so one corpus trains
both. Training ran to adapter checkpoint 2019 (2019 steps, a quarter epoch); the
adapter was merged into the base weights and the merge was quantized to Q4_K_M.

Every layer of that build is hashed and recorded in
[provenance.json](provenance.json): the corpus content, the packed training
shards, the adapter checkpoint, the LoRA GGUF, and the final quantized GGUF.
Given the same inputs, an outside observer can re-derive and verify each link.

The training corpus is proprietary and is not distributed with the model.

## What this model is for

A local-first coding companion at 32B scale: code completion, functions,
refactors, test writing, and tool-calling workflows where your code must not
leave your machine. It pairs naturally with a verification loop (propose, test,
accept only what passes).

## Known boundaries

- No claimed capability uplift over the base model.
- No benchmark scores yet; only a deterministic generation smoke is recorded.
  See [BENCHMARKS.md](BENCHMARKS.md).
- This is a quarter-epoch continued-pretraining adaptation, a light domain pass,
  not a full retrain.
- Knowledge cutoff and multilingual behavior follow the base model.
