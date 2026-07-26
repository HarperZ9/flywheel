# Flywheel-Local-Coder-32B Usage

Status: the commands below were exercised locally; benchmark-grade usage examples are pending.

## Ollama

The Modelfile lives next to the artifact:

```text
E:\local-model-run\gguf-work-32b\Modelfile
```

Create and run:

```powershell
ollama create flywheel-local-coder-32b -f E:\local-model-run\gguf-work-32b\Modelfile
ollama run flywheel-local-coder-32b
```

## llama.cpp

Direct completion against the GGUF, matching the deterministic smoke configuration (temp 0, seed 7):

```powershell
llama-cli -m E:\local-model-run\gguf-work-32b\telos-coder-32b-cpt2019-q4_k_m.gguf --temp 0 --seed 7 -n 64 -p "<prompt>"
```

Reruns at temp 0, seed 7 are byte-identical (smoke verdict MATCH).

## Harness endpoint profile

The flywheel harness reaches the model through this endpoint profile:

- backend: `ollama`
- model: `flywheel-local-coder-32b`
- base URL: `http://127.0.0.1:11434`

## Required before publishing usage examples

- An endpoint gate artifact passes, or the failure mode is documented.
- Prompt examples use the same task-set contract as benchmark runs.
- No examples require secrets or private files.
