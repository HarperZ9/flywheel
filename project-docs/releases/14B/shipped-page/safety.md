# Safety and Claims

This page states plainly what this model does and does not claim, so you can
weigh it without reading between the lines.

## What we claim, and the evidence

- **The artifact is what it says it is.** The build is retraceable hash by
  hash: corpus content, packed training shards, adapter checkpoint, and the
  final GGUF are each recorded in [provenance.json](provenance.json), and
  [checksums.sha256](checksums.sha256) ties the chain to the exact file you
  downloaded.
- **Reruns are reproducible.** At temperature 0 with a fixed seed, completions
  are byte-identical across runs (recorded output SHA-256
  `970af540244384407918aa3b0172b403c24d17800e3c514c3c19937d88c7e636`).
- **Benchmark numbers carry their intervals.** Everything we measured is on
  the [benchmarks page](BENCHMARKS.md) with confidence intervals and the JSON
  artifacts beside it.

## What we do not claim

- **No capability uplift over the base model.** Our own measurement of that
  difference includes zero, and we say so rather than rounding up.
- **No public leaderboard standing.** HumanEval, MBPP, and similar suites have
  not been run yet.
- **No safety tuning beyond the base model.** Refusal behavior, bias, and
  content boundaries follow Qwen2.5-Coder-14B-Instruct. We have not measured
  or modified them, so treat them as inherited and unaudited here.

## Sensible boundaries for use

- Treat generated code the way you would treat code from any assistant: run
  your tests, review before shipping, and never execute generated code against
  production systems unreviewed.
- The model runs entirely locally and sends nothing anywhere. Network behavior
  is a property of the runtime you choose (Ollama, llama.cpp), not the weights.
- Keep secrets out of prompts as a habit. Nothing in this release requires
  secrets, keys, or private files to use.

## If you find a problem

Open an issue on the model repo with the prompt, the runtime and version, and
the observed output. A reproducible report at temperature 0 is the fastest
path to a fix, because we can replay it exactly.
