# Usage Guide

Everything below assumes you downloaded this repo folder, so the GGUF and the
Modelfile sit together in your working directory.

## Verify your download (optional, 30 seconds)

```
sha256sum telos-coder-32b-cpt2019-q4_k_m.gguf
```

Compare against [checksums.sha256](checksums.sha256). A match means you hold the
exact bytes the provenance chain describes.

## Ollama

```
ollama create flywheel-local-coder-32b -f Modelfile
ollama run flywheel-local-coder-32b
```

That gives you interactive chat. Ollama also exposes an OpenAI-compatible API
the moment the model is created, so any tool that speaks the OpenAI chat format
can use the model locally:

```
curl http://127.0.0.1:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"flywheel-local-coder-32b","messages":[{"role":"user","content":"Write a Python function that merges overlapping intervals."}]}'
```

Point your editor plugin, agent framework, or script at
`http://127.0.0.1:11434/v1` with model name `flywheel-local-coder-32b` and you
have a private, zero-cost coding endpoint. On an 18.5 GB model, first-token
latency depends on how much of the model fits in VRAM; see the
[spec sheet](SPECS.md) for hardware guidance.

## llama.cpp

Interactive chat, one command:

```
llama-cli -m telos-coder-32b-cpt2019-q4_k_m.gguf -cnv
```

Deterministic completion (the exact configuration our receipt uses):

```
llama-cli -m telos-coder-32b-cpt2019-q4_k_m.gguf --temp 0 --seed 7 -n 64 -p "your prompt"
```

At temperature 0 with a fixed seed, reruns are byte-identical. That is not a
nicety: it is what lets a receipt be re-checked by someone who is not us.

## The adapter

If you would rather apply the trained delta yourself, or requantize at another
precision, pull the LoRA adapter and work from your own copy of the base:

```
hf download zaindanaharper/flywheel-local-coder-32b telos-coder-32b-cpt2019-lora.gguf --local-dir .
```

The base weights are never republished here; bring your own copy of
`Qwen2.5-Coder-32B-Instruct` (Apache-2.0) and apply the adapter with
llama.cpp's `--lora`, or merge and requantize with `llama-export-lora` +
`llama-quantize`.

## Tool calling

The model supports tool/function calling through Ollama's OpenAI-compatible
endpoint: pass a `tools` array in the request as you would with any OpenAI-style
API.

## Tips

- Give it the full contract. Precise asks (exact exception messages, edge cases,
  output format) get precise answers.
- Pair it with your tests. Its natural habitat is a propose-then-verify loop:
  let it write, run your tests, keep what passes.
- 32,768-token context: enough for a large file plus conversation, not an entire
  repository. Feed it the relevant slice.
- If speed matters more than capacity, the 14B sibling runs the same way at less
  than half the memory.
