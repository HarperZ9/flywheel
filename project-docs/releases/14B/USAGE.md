# Flywheel-Local-Coder-14B Usage

Status: draft. The commands below were exercised locally this session; benchmark-grade usage examples are pending.

## Ollama

The Modelfile lives next to the artifact:

```text
E:\local-model-run\release\flywheel-local-coder-14b\Modelfile
```

Create and run:

```powershell
ollama create flywheel-local-coder-14b -f E:\local-model-run\release\flywheel-local-coder-14b\Modelfile
ollama run flywheel-local-coder-14b
```

## llama.cpp

Direct completion against the GGUF, matching the deterministic smoke configuration (temp 0, seed 7):

```powershell
llama-completion -m E:\local-model-run\release\flywheel-local-coder-14b\telos-coder-14b-cpt2020-q4_k_m.gguf --temp 0 --seed 7 -n 48 -p "<prompt>"
```

Reruns at temp 0, seed 7 are byte-identical (smoke verdict MATCH).

## Harness endpoint profile

The flywheel harness reaches the model through this endpoint profile:

- backend: `ollama`
- model: `flywheel-local-coder-14b`
- base URL: `http://127.0.0.1:11434`

## Required before publishing usage examples

- Endpoint gate passes or the failure mode is clearly documented.
- Prompt examples use the same task-set contract as benchmark runs.
- No examples require secrets or private files.
