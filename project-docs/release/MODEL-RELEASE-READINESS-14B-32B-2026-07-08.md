# Model Release Readiness: 14B And 32B - 2026-07-08

## Summary

No model should be published yet.

14B has a plausible release candidate path after evidence work.
32B is not publishable in current form; it is smoke-only.

## Current Artifacts

Base models:
- `E:\local-model-run\models\Qwen2.5-Coder-14B-Instruct`
- `E:\local-model-run\models\Qwen2.5-Coder-32B-Instruct`

Project-owned derivatives:
- 14B LoRA CPT adapter: `E:\local-model-run\checkpoints\phase2-linux-qlora-cpt-14b\checkpoint-2020`
- 32B smoke adapter: `E:\local-model-run\checkpoints\phase2-linux-qlora-cpt-32b-smoke\checkpoint-2`

Missing artifact:
- No `.gguf` file was found by the release-lane subagent under `E:\local-model-run`, `C:\dev\local-model`, or `C:\tmp`.

## Recommended Names

14B:
- Public LoRA: `telos-coder-14b-cpt2020-lora`
- Public GGUF/Ollama after artifact exists: `telos-coder-14b-cpt2020-q4_k_m`

32B:
- Internal current state: `telos-coder-32b-smoke-checkpoint2`
- Future LoRA after full CPT/eval: `telos-coder-32b-cpt<step>-lora`
- Future GGUF/Ollama after packaging: `telos-coder-32b-cpt<step>-q4_k_m`

## Publish Blockers

14B:
- Model card still needs base model, license, training data, training recipe, evals, limitations, and intended/out-of-scope use.
- Need file manifests and SHA256 checksums.
- Need benchmark evidence from real non-dry runs.
- Need safety/PII/proprietary-data scan evidence.
- Need GGUF/Ollama artifact if publishing the quantized runtime package.

32B:
- Only a two-step smoke adapter exists.
- Needs full CPT training run.
- Needs benchmark evidence.
- Needs model card and release artifact layout.
- Should remain internal until complete.

## Evidence Required Before Publish

File evidence:
- base model reference and license
- adapter files
- tokenizer files
- dataset receipt
- release manifest
- SHA256 checksums
- GGUF and Modelfile if publishing Ollama/GGUF

Benchmark evidence:
- 14B base vs 14B adapter
- 32B base vs future 32B full adapter
- M7 easy/hard/expert
- N >= 100 for public claims
- same task set for baselines
- confidence intervals
- raw receipts and reproducibility check

Safety evidence:
- training corpus provenance
- secret scan
- PII scan
- proprietary-data boundary statement
- intended use and excluded use
- code-risk limitations

## Later Publish Steps

Do not run until evidence gates pass.

```powershell
hf version
git-lfs version
ollama --version

hf auth login
hf repo create HarperZ9/telos-coder-14b-cpt2020-lora --type model --private --exist-ok
hf upload-large-folder HarperZ9/telos-coder-14b-cpt2020-lora E:\local-model-run\release\telos-coder-14b-cpt2020-lora --repo-type model --num-workers 4

hf repo create HarperZ9/telos-coder-14b-cpt2020-q4_k_m --type model --private --exist-ok
hf upload-large-folder HarperZ9/telos-coder-14b-cpt2020-q4_k_m E:\local-model-run\release\telos-coder-14b-cpt2020-q4_k_m --repo-type model --num-workers 4

ollama signin
ollama create HarperZ9/telos-coder-14b-cpt2020-q4_k_m -f E:\local-model-run\release\telos-coder-14b-cpt2020-q4_k_m\Modelfile
ollama show HarperZ9/telos-coder-14b-cpt2020-q4_k_m
ollama push HarperZ9/telos-coder-14b-cpt2020-q4_k_m
```

## Next Loop

System activity -> serve and benchmark the 14B adapter.
Observed friction -> live server currently reports base 14B, not adapter.
Capability improvement -> release manifest and benchmark runner profile for adapter-vs-base.
Future improvement -> model naming/publishing decisions become evidence-driven instead of manual.
Next trigger -> restart `serve.py` with `SERVE_ADAPTER_PATH=E:\local-model-run\checkpoints\phase2-linux-qlora-cpt-14b\checkpoint-2020` and run smoke/M7 benchmarks.
