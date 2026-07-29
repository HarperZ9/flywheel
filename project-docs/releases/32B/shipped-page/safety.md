# Safety and Claims

This page states plainly what this model does and does not claim, so you can
weigh it without reading between the lines.

## What we claim, and the evidence

- **The artifact is what it says it is.** The build is retraceable hash by
  hash: corpus content, packed training shards, adapter checkpoint, the LoRA
  GGUF, and the final quantized GGUF are each recorded in
  [provenance.json](provenance.json), and [checksums.sha256](checksums.sha256)
  ties the chain to the exact file you downloaded.
- **Reruns are reproducible.** Served at temperature 0 with a fixed seed,
  generations are byte-identical across runs (recorded generation hash prefix
  `403b2e8b21df9f55`).

## What we do not claim

- **No capability uplift over the base model.** We have not measured one, so we
  do not assert one.
- **No benchmark standing at all, yet.** Unlike the 14B, this model carries no
  executed benchmark artifacts. HumanEval, MBPP, hard-set, and similar suites
  have not been run. See [BENCHMARKS.md](BENCHMARKS.md).
- **No safety tuning beyond the base model.** Refusal behavior, bias, and
  content boundaries follow Qwen2.5-Coder-32B-Instruct. We have not measured or
  modified them, so treat them as inherited and unaudited here.

## Sensible boundaries for use

- Treat generated code the way you would treat code from any assistant: run your
  tests, review before shipping, and never execute generated code against
  production systems unreviewed.
- The model runs entirely locally and sends nothing anywhere. Network behavior
  is a property of the runtime you choose (Ollama, llama.cpp), not the weights.
- Keep secrets out of prompts as a habit. Nothing in this release requires
  secrets, keys, or private files to use.

## If you find a problem

Open an issue on the model repo with the prompt, the runtime and version, and
the observed output. A reproducible report at temperature 0 is the fastest path
to a fix, because we can replay it exactly.
