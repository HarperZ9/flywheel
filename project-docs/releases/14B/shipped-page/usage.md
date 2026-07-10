# Usage Guide

Everything below assumes you downloaded this repo folder, so the GGUF and the
Modelfile sit together in your working directory.

## Verify your download (optional, 10 seconds)

```
sha256sum telos-coder-14b-cpt2020-q4_k_m.gguf
```

Compare against [checksums.sha256](checksums.sha256). A match means you hold
the exact bytes the provenance chain describes.

## Ollama

```
ollama create flywheel-local-coder-14b -f Modelfile
ollama run flywheel-local-coder-14b
```

That gives you interactive chat. Ollama also exposes an OpenAI-compatible API
the moment the model is created, so any tool that speaks the OpenAI chat format
can use the model locally:

```
curl http://127.0.0.1:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"flywheel-local-coder-14b","messages":[{"role":"user","content":"Write a Python function that merges overlapping intervals."}]}'
```

Point your editor plugin, agent framework, or script at
`http://127.0.0.1:11434/v1` with model name `flywheel-local-coder-14b` and you
have a private, zero-cost coding endpoint.

## llama.cpp

Interactive chat, one command:

```
llama-cli -m telos-coder-14b-cpt2020-q4_k_m.gguf -cnv
```

Deterministic completion (the exact configuration our receipts use):

```
llama-completion -m telos-coder-14b-cpt2020-q4_k_m.gguf --temp 0 --seed 7 -n 256 -p "your prompt"
```

At temperature 0 with a fixed seed, reruns are byte-identical. That is not a
nicety: it is what lets a benchmark number on the [benchmarks page](BENCHMARKS.md)
be re-checked by someone who is not us.

## Tool calling

The model supports tool/function calling through Ollama's OpenAI-compatible
endpoint: pass a `tools` array in the request as you would with any OpenAI-style
API.

## Tips

- Give it the full contract. The model was benchmarked on prompts that state
  every rule (exact exception messages, edge cases, output format). It rewards
  precise asks.
- Pair it with your tests. Its natural habitat is a propose-then-verify loop:
  let it write, run your tests, keep what passes.
- 32,768-token context: enough for a large file plus conversation, not an
  entire repository. Feed it the relevant slice.
