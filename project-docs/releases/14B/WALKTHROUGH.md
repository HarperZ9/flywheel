# Flywheel Local Coder 14B: A Complete Walkthrough

Date: 2026-07-09
Release name: `Flywheel-Local-Coder-14B`
Artifact: `telos-coder-14b-cpt2020-q4_k_m.gguf`

This guide assumes nothing. If you have never run a language model on your
own computer, start at the top and go step by step. Every command is
copy-pasteable. Windows PowerShell is the primary path; WSL and Linux
variants appear where they differ.

## What this is

Flywheel Local Coder 14B is a 14 billion parameter coding model that runs
entirely on your own machine. It is built from `Qwen2.5-Coder-14B-Instruct`
(Apache-2.0 licensed) plus a continued-pretraining adapter
(`checkpoint-2020`, QLoRA, final train_loss 0.035), merged and quantized to
Q4_K_M. The whole model is one file of 8,988,110,880 bytes, just under 9 GB.

The model ships with something a plain model download does not have: a
provenance chain. Every layer of its construction, from the training corpus
to the shards to the adapter to the final file, has a recorded hash, and you
can check the final link yourself with one command. Step 5 shows how.

The model is one half of the story. The other half is the flywheel harness,
a small verification loop that runs beside the model: the model proposes
code, an oracle (a real test suite) checks it, and every accepted answer
carries a receipt that anyone can re-run. The harness is the durable part
of this project. The model is the replaceable part, and that is by design.

## Why local

There is something quietly wonderful about a capable coding model living
in a single file on your own disk. It works on an airplane. It works when
an API is down. Your prompts and your code never leave your machine. It
costs nothing per token, so you can experiment freely, rerun things ten
times, and let curiosity set the pace. And because the file never changes
underneath you, the same prompt at temperature 0 gives the same answer
today, tomorrow, and next year. That stability is what makes the receipts
in Step 4 possible at all.

## What you need

- Disk: about 9 GB for the model file, plus a little working room.
- Memory: 16 GB of system RAM is comfortable for CPU-only use. With less,
  it may still run, just slower.
- GPU: optional. A GPU with roughly 12 GB of memory can hold the whole
  model and is noticeably faster. Without one, the CPU does all the work
  and generation is slower but perfectly usable for study and small tasks.
- Software: Ollama (Step 1). For the harness and benchmark steps, Python
  3.11 or newer and `pytest`.
- The release folder. In this walkthrough it lives at
  `E:\local-model-run\release\flywheel-local-coder-14b` and contains the
  GGUF file, a `Modelfile`, `LICENSE`, the release documents, and
  `checksums.sha256`. If your copy lives somewhere else, substitute your
  path throughout.

## Step 1: Install Ollama

Ollama is a small program that loads GGUF model files and serves them on a
local address, `http://127.0.0.1:11434`. Nothing it does leaves your
machine.

Windows (PowerShell):

```powershell
winget install Ollama.Ollama
```

Or download the installer from https://ollama.com/download.

WSL / Linux:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Confirm it is installed:

```powershell
ollama --version
```

## Step 2: Create the model from the Modelfile

The release folder includes a `Modelfile`, a one-line recipe that points
Ollama at the GGUF file:

```powershell
ollama create flywheel-local-coder-14b -f "E:\local-model-run\release\flywheel-local-coder-14b\Modelfile"
```

The `FROM` line inside the Modelfile uses an absolute path. If your release
folder lives at a different path, write a fresh Modelfile next to the GGUF
and create from that instead:

```powershell
Set-Location "E:\local-model-run\release\flywheel-local-coder-14b"
Set-Content -Path .\Modelfile.local -Value "FROM .\telos-coder-14b-cpt2020-q4_k_m.gguf" -Encoding utf8
ollama create flywheel-local-coder-14b -f .\Modelfile.local
```

Check that Ollama now knows the model:

```powershell
ollama list
```

You should see `flywheel-local-coder-14b` in the list.

## Step 3: Your first generation

```powershell
ollama run flywheel-local-coder-14b "Write a Python function that run-length encodes a string, with a short docstring."
```

The first response takes a little while because the model is loading from
disk into memory. After that, it stays warm and answers faster. You can
also just type `ollama run flywheel-local-coder-14b` for an interactive
session; type `/bye` to leave.

Take a moment here. A 14 billion parameter model just wrote code for you
on your own hardware, with no account, no key, and no network.

## Step 4: Connect the flywheel harness

Generation alone is half the loop. The harness closes it: propose, verify
against an oracle, and witness the result as MATCH or DRIFT. Every accepted
answer carries a re-checkable proof envelope, so a result is never just
"the model said so."

You need the `local-model` repository (this walkthrough lives inside it),
Python 3.11 or newer, and pytest:

```powershell
Set-Location C:\dev\local-model
python --version
pip install pytest
```

The harness reaches the model through its Ollama endpoint profile: backend
`ollama` at `http://127.0.0.1:11434`. Confirm the endpoint is alive and the
model is present:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags | Select-Object -ExpandProperty models | Select-Object name
```

WSL / Linux:

```bash
curl -s http://127.0.0.1:11434/api/tags
```

If `flywheel-local-coder-14b` appears, the harness can see your model and
you are ready to run verified inference.

## Step 5: Verify the provenance chain yourself

This is the part of the release we most hope you actually do, because you
can. No trust required, just two commands and a comparison.

The recorded chain lives in
`C:\dev\local-model\tasks\research\gguf_ship_manifest_checkpoint2020.json`
and reads, layer by layer:

| Layer | Hash |
| --- | --- |
| Training corpus content (17,997 files) | `68345cdc6667f20d1678ac0a9139edc170348dfdebb9ae6045cde3d204f4fe62` |
| Packed training shards | `018798dfce7d4c86f5a6ea502a383553220f2e76facfe76acbe52b1c278ae543` |
| Adapter checkpoint (checkpoint-2020) | `4de07c6ea342d1cc200d4a6e2b28a63f6ee37f34c5c0926c35d8c7db74d38d0f` |
| Released GGUF | `613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be` |

The dataset receipt behind the corpus layer is
`tasks/research/dataset_receipt_checkpoint2020.json`.

Check the file you have against the last link in the chain:

```powershell
Get-FileHash "E:\local-model-run\release\flywheel-local-coder-14b\telos-coder-14b-cpt2020-q4_k_m.gguf" -Algorithm SHA256
(Get-Item "E:\local-model-run\release\flywheel-local-coder-14b\telos-coder-14b-cpt2020-q4_k_m.gguf").Length
```

PowerShell prints the hash in uppercase; compare it case-insensitively. The
hash should be `613DB240...4064BE` matching the table above, and the length
should be exactly `8988110880`.

WSL / Linux:

```bash
cd /mnt/e/local-model-run/release/flywheel-local-coder-14b
sha256sum telos-coder-14b-cpt2020-q4_k_m.gguf
```

To check every file listed in `checksums.sha256`:

```powershell
Set-Location "E:\local-model-run\release\flywheel-local-coder-14b"
Get-Content .\checksums.sha256 | ForEach-Object {
    $parts = $_ -split '\s+', 2
    $expected = $parts[0]
    $name = $parts[1].Trim()
    if (-not (Test-Path $name)) { "MISSING  $name"; return }
    $actual = (Get-FileHash -Path $name -Algorithm SHA256).Hash.ToLower()
    if ($actual -eq $expected) { "OK       $name" } else { "FAIL     $name" }
}
```

WSL / Linux:

```bash
sha256sum -c checksums.sha256 --ignore-missing
```

A `MISSING` line means the checksum list carries an entry for a file that
is not in your copy of the folder; the line that matters most is the GGUF
itself. Any `FAIL` line means the file does not match the release and
should not be used.

The earlier links (corpus, shards, adapter) are re-derivable in the same
way if you have those artifacts; the manifest records the expected value
for each so the whole chain is checkable, layer by layer, by whoever holds
the layer.

One more small delight: the release was smoke-tested with `llama-completion`
at temperature 0, seed 7, 48 tokens, and produced byte-identical output
across reruns (recorded verdict MATCH, output sha256
`970af540244384407918aa3b0172b403c24d17800e3c514c3c19937d88c7e636`). Same
bytes in, same bytes out. Local models can be this quiet and repeatable.

## Step 6: Reproduce the benchmark

The benchmark run for this release used the M7 easy held-out set: 8 coding
tasks, each with hidden tests, run through four harness arms (single shot,
verified inference, flat best-of-4, and no-search). To rerun it yourself,
from the repository root with Ollama serving the model:

```powershell
Set-Location C:\dev\local-model
python scripts/run_m7_eval.py --local-primary ollama --local-model flywheel-local-coder-14b --out artifacts\m7_scorecard_local.json
```

WSL / Linux (with Ollama reachable at 127.0.0.1:11434):

```bash
cd /path/to/local-model
python3 scripts/run_m7_eval.py --local-primary ollama --local-model flywheel-local-coder-14b --out artifacts/m7_scorecard_local.json
```

What the recorded run produced, and what you should expect to see:

```
=== M7 eval (harness lift on the held-out set) ===
  single_shot: pass=100% (8/8) avg_oracle=1.0 receipts=100%
  verified_inference: pass=100% (8/8) avg_oracle=4.0 receipts=100%
  flat_n: pass=100% (8/8) avg_oracle=4.0 receipts=100%
  no_search: pass=100% (8/8) avg_oracle=1.0 receipts=100%
  verdict (verified_inference >= single_shot): MATCH
```

An honest note on what this does and does not show. All four arms passed
8 of 8, and every receipt re-checked. That demonstrates the release
generates correct code on this set with reproducible receipts. It does not
show one arm beating another, because a set where everything passes cannot
tell arms apart. This easy set is saturated. No capability uplift is
claimed from it, or anywhere else in this release. A 38-task hard-set run,
the instrument that can actually discriminate, is in flight; its results
are pending and will be published when it lands. The full methodology,
written so an outside observer can rerun everything, is at
`project-docs/reports/BENCHMARK-METHODOLOGY-OUTSIDE-OBSERVER-2026-07-09.md`.

## Step 7: Read a receipt

Open the scorecard you just produced:

```powershell
Get-Content C:\dev\local-model\artifacts\m7_scorecard_local.json
```

The scorecard is written to be read without tribal knowledge. Three things
to look for:

- `arms`: one block per configuration, with `n_tasks`, `pass_rate`,
  `avg_oracle_calls`, `avg_candidates`, and `receipt_reproducibility`.
- `metrics`: each metric declares its own range and which direction is
  good (`pass_rate` higher, `avg_oracle_calls` lower), so the numbers
  carry their own reading instructions.
- `meta`: the `model_ref` (for this release,
  `ollama:flywheel-local-coder-14b`), the task count, and a note naming
  what was compared.

Underneath the scorecard, each accepted answer travels with a proof
envelope. Its fields are the whole story of one verification: `task_id`,
the exact `candidate` code, the `oracle_cmd` that judged it, the
`oracle_output_hash` (a canonical hash of the test outcomes, deliberately
excluding timing noise), the `verdict`, the `model_ref`, the `seed`, and
the `prompt_hash`. A witness re-runs `oracle_cmd` against the candidate
and recomputes the hash: MATCH means a third party reproduced the verdict,
DRIFT means the envelope and reality diverge, UNVERIFIABLE means the
oracle could not be re-run. That is the entire trust story, and every part
of it is in your hands: you hold the model file, the tasks, the tests, and
the receipts, so "you can check everything yourself" is not a slogan here,
it is a command you have already run.

## Where to go next

- The rest of this release folder: `README.md`, `MODEL_CARD.md`,
  `PROVENANCE.md`, `USAGE.md`, and `BENCHMARKS.md` in
  `project-docs/releases/14B/`.
- The methodology document, if you want to go from "I ran it" to "I could
  audit it":
  `project-docs/reports/BENCHMARK-METHODOLOGY-OUTSIDE-OBSERVER-2026-07-09.md`.
- The hard-set results, once the pending 38-task run lands. That is where
  the arms can finally be told apart.
- Your own prompts. The model is on your disk and the meter never runs.
  Try the interactive session, feed it your own small problems, and watch
  how far a single 9 GB file on ordinary hardware can go.
- Swapping the model. The harness speaks to anything Ollama can serve.
  The loop of propose, verify, and witness stays the same; the model
  underneath is yours to choose.
