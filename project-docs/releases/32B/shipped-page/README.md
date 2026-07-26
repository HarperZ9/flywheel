---
license: apache-2.0
base_model: Qwen/Qwen2.5-Coder-32B-Instruct
tags:
  - code
  - gguf
  - qlora
  - local-first
  - verified-inference
pipeline_tag: text-generation
library_name: gguf
---

# Flywheel-Local-Coder-32B

A 32-billion-parameter coding model in a single Q4_K_M file that runs entirely
on your own machine. It takes Qwen2.5-Coder-32B-Instruct and continues its
pretraining on the same 66-million-token corpus behind the 14B, drawn from a
real working development ecosystem, then packs the merge into one GGUF just
under 19 GB. Your prompts and your code never leave your disk. And if you ever
care to look, the whole build, corpus to weights, can be retraced hash by hash.

This is the larger sibling of [Flywheel-Local-Coder-14B](https://huggingface.co/zaindanaharper/flywheel-local-coder-14b):
more capacity, the same local-first stance and the same retraceable chain.

## Run it in two commands

```
hf download zaindanaharper/flywheel-local-coder-32b telos-coder-32b-cpt2019-q4_k_m.gguf --local-dir .
llama-cli -m telos-coder-32b-cpt2019-q4_k_m.gguf -cnv
```

Prefer Ollama? Download the repo folder so the GGUF and the Modelfile sit
together, then:

```
ollama create flywheel-local-coder-32b -f Modelfile
ollama run flywheel-local-coder-32b
```

No conversion step, no shards, no Python environment. The [usage guide](usage.md)
covers chat, deterministic completion, an OpenAI-compatible local endpoint, and
how to verify your download against the published checksums.

## Specs at a glance

| | |
|---|---|
| Parameters | 32.5B (qwen2 architecture) |
| Context length | 32,768 tokens |
| Quantization | Q4_K_M, single GGUF file |
| File size | 18.5 GB (19,851,336,480 bytes) |
| Capabilities | chat, code completion, tool calling |
| Base model | Qwen2.5-Coder-32B-Instruct |
| Training | QLoRA continued pretraining, 66.2M tokens across 17,997 files |
| License | Apache-2.0 (with Qwen attribution) |
| SHA-256 | `65e6133fbe4d12579a776047a71bebb98ab86f9e3d343ed821b51dac0ce312f4` |

Full details in the [spec sheet](SPECS.md).

## What to expect

This is a local-first coding companion at 32B scale: completions, functions,
refactors, and tool-calling on your own hardware, with your code staying home.
It needs more room than the 14B, roughly 20 GB of memory for the weights plus
context, so it is happiest on a 24 GB GPU or a machine with generous RAM; see
the [spec sheet](SPECS.md) for hardware guidance.

We publish measurements, not adjectives, and we are precise about which we have.
Unlike the 14B, this model does not yet carry benchmark scores. Its only
recorded behavioral receipt today is a deterministic generation smoke: at
temperature 0 with a fixed seed, reruns are byte-identical. We make no
capability-uplift claim over the base model. Benchmarks are pending and will
ship with the JSON they came from and the method to re-run them, exactly as the
14B's [benchmarks page](BENCHMARKS.md) already does. Until then, the honest
statement is: a verified, retraceable continued-pretraining build, not a scored
one.

## Also in this repo

- `telos-coder-32b-cpt2019-q4_k_m.gguf`: the runnable merged model (above).
- `telos-coder-32b-cpt2019-lora.gguf`: the QLoRA adapter (268 MB). Apply the
  trained delta to your own copy of the base, or requantize from it at another
  precision. The base weights themselves are never republished here.

## The documents

- [Usage guide](usage.md): run it with Ollama, llama.cpp, or as a local API.
- [Benchmarks](BENCHMARKS.md): what is measured so far, and what is still pending.
- [Spec sheet](SPECS.md): hardware guidance, training details, formats.
- [Safety and claims](safety.md): what this model does and does not claim.
- [Model card](MODEL_CARD.md): the full technical card.
- [provenance.json](provenance.json) and [checksums.sha256](checksums.sha256):
  the retraceable chain from corpus to the exact bytes you downloaded.

## License and attribution

Apache-2.0. Built on Qwen2.5-Coder-32B-Instruct by the Qwen team; see LICENSE
for the attribution notice. The training corpus is proprietary to the author;
the shipped weights carry no third-party code beyond the base model, and the
base model is never republished on its own.
