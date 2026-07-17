# Spec Sheet

## The model

| | |
|---|---|
| Name | Flywheel-Local-Coder-14B |
| Architecture | qwen2 (transformer, decoder-only) |
| Parameters | 14.8B |
| Context length | 32,768 tokens |
| Embedding size | 5,120 |
| Capabilities | chat, code completion, tool calling |
| Base model | Qwen/Qwen2.5-Coder-14B-Instruct |
| License | Apache-2.0 with Qwen attribution |

## The file

| | |
|---|---|
| Format | GGUF, single file |
| Quantization | Q4_K_M |
| Size | 8.99 GB (8,988,110,880 bytes) |
| SHA-256 | `613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be` |
| Verify | `sha256sum telos-coder-14b-cpt2020-q4_k_m.gguf` and compare with [checksums.sha256](checksums.sha256) |

## Hardware guidance

- **GPU**: fits fully on a 24 GB card with room for context. Smaller cards work
  with partial CPU offload; expect lower speed.
- **CPU only**: works. Budget roughly 12 GB of free RAM for the weights plus
  context; generation is slower but entirely usable for chat and completion.
- **Disk**: 9 GB for the file itself.

Runs anywhere llama.cpp or Ollama runs: Windows, Linux, macOS.

## How it was trained

Continued pretraining (QLoRA) of the base model on a 66.2-million-token corpus
of 17,997 files from a real, working development ecosystem: production code,
tests, documentation, and research notes. Training ran to adapter checkpoint
2020 (final train loss 0.035), the adapter was merged into the base weights,
and the merge was quantized to Q4_K_M.

Every layer of that build is hashed and recorded in
[provenance.json](provenance.json): the corpus content, the packed training
shards, the adapter checkpoint, and the final GGUF. Given the same inputs, an
outside observer can re-derive and verify each link of the chain.

The training corpus is proprietary and is not distributed with the model.

## What this model is for

A local-first coding companion: code completion, small functions, refactors,
test writing, and tool-calling workflows where your code must not leave your
machine. It pairs naturally with a verification loop (propose, test, accept
only what passes), which is exactly how we benchmark it.

## Known boundaries

- No claimed capability uplift over the base model; see [BENCHMARKS.md](BENCHMARKS.md).
- No public leaderboard scores yet.
- Knowledge cutoff and multilingual behavior follow the base model.
- A 32B sibling is planned but not yet trained; nothing is published for it.
