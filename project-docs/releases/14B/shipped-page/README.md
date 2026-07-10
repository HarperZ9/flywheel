---
license: apache-2.0
base_model: Qwen/Qwen2.5-Coder-14B-Instruct
tags:
  - code
  - gguf
  - qlora
  - local-first
  - verified-inference
pipeline_tag: text-generation
library_name: gguf
---

# Flywheel-Local-Coder-14B

A 14.8B coding model in a single file that runs entirely on your own machine.
It takes Qwen2.5-Coder-14B-Instruct and continues its pretraining on a
66-million-token corpus drawn from a real working development ecosystem, then
packs the result into one Q4_K_M GGUF just under 9 GB. Your prompts and your
code never leave your disk. And if you ever care to look, the whole build,
corpus to weights, can be retraced hash by hash.

## Run it in two commands

```
hf download zaindanaharper/flywheel-local-coder-14b telos-coder-14b-cpt2020-q4_k_m.gguf --local-dir .
llama-cli -m telos-coder-14b-cpt2020-q4_k_m.gguf -cnv
```

Prefer Ollama? Download the repo folder so the GGUF and the Modelfile sit
together, then:

```
ollama create flywheel-local-coder-14b -f Modelfile
ollama run flywheel-local-coder-14b
```

No conversion step, no shards, no Python environment. The [usage guide](usage.md)
covers chat, deterministic completion, an OpenAI-compatible local endpoint, and
how to verify your download against the published checksums.

## Specs at a glance

| | |
|---|---|
| Parameters | 14.8B (qwen2 architecture) |
| Context length | 32,768 tokens |
| Quantization | Q4_K_M, single GGUF file |
| File size | 8.99 GB (8,988,110,880 bytes) |
| Capabilities | chat, code completion, tool calling |
| Base model | Qwen2.5-Coder-14B-Instruct |
| Training | QLoRA continued pretraining, 66.2M tokens across 17,997 files |
| License | Apache-2.0 (with Qwen attribution) |
| SHA-256 | `613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be` |

Full details in the [spec sheet](SPECS.md).

## What to expect

This is a local-first daily coding companion: completions, small functions,
refactors, and tool-calling on your own hardware, with your code staying home.

We publish measurements, not adjectives. On our internal evaluation sets the
model passes 8 of 8 baseline tasks and 8 of 10 deliberately contract-heavy
hard tasks in a single attempt, with confidence intervals attached to every
number. We do not claim a capability uplift over the base model: our own
measurement of that difference includes zero, and the [benchmarks page](BENCHMARKS.md)
says so plainly. Every number there ships with the JSON it came from and the
method to re-run it.

## The documents

- [Usage guide](usage.md): run it with Ollama, llama.cpp, or as a local API.
- [Benchmarks](BENCHMARKS.md): what we measured, the intervals, and how to re-run it.
- [Spec sheet](SPECS.md): hardware guidance, training details, formats.
- [Safety and claims](safety.md): what this model does and does not claim.
- [Model card](MODEL_CARD.md): the full technical card.
- [provenance.json](provenance.json) and [checksums.sha256](checksums.sha256):
  the retraceable chain from corpus to the exact bytes you downloaded.

## License and attribution

Apache-2.0. Built on Qwen2.5-Coder-14B-Instruct by the Qwen team; see LICENSE
for the attribution notice. The training corpus is proprietary to the author;
the shipped weights carry no third-party code beyond the base model.
