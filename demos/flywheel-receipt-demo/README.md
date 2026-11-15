<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/flywheel-receipt-demo/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/flywheel-receipt-demo/main/docs/art/hero-light.svg" alt="flywheel-receipt-demo: Run a re-derivable receipt in one command and catch a forged one. A chain of small linked squares, each holding a few ruled lines, winds inward to a bright core. One mark is labelled MATCH." width="100%">
</picture>

# flywheel-receipt-demo

Run a re-derivable receipt in one command and catch a forged one.

```
pip install flywheel-verify pytest
```

[![license](https://img.shields.io/badge/license-FSL--1.1--MIT-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/flywheel-receipt-demo/blob/main/LICENSE)

Run Flywheel's re-derivable receipt path in one command, and see how it composes
with hardware-attested inference.

Flywheel is a self-hostable verification workstation for AI-assisted work. Its
backbone is one rule: no receipt, no accept, and no learned model on the path that
accepts an answer. Every accepted result carries a receipt that a third party
re-runs offline to reach the same verdict.

This repository does two things:

1. It runs that receipt path end to end on your machine, with no API key, no GPU,
   and no network.
2. It lays out how the receipt path composes with hardware-attested inference, so
   one verification covers both what ran and whether the answer holds up. NEAR AI's
   confidential inference is the worked example.

## Quick start

```
pip install flywheel-verify pytest
cd demo
python run_demo.py
```

The demo sends a real coding task through the engine, emits a proof receipt, and
re-derives that receipt in a separate process to MATCH. Then it forges the receipt
and shows the re-derivation catch the forgery as DRIFT. It prints each step and
exits 0 when the receipt path checks out.

You do not have to trust the script. After it runs, re-check the receipt yourself:

```
python -m harness.verify_receipt --receipt out/receipt.json --task-dir task
```

Edit any field in the receipt and run it again. It reports DRIFT.

## See it work, step by step

The [animated explainer](https://harperz9.github.io/repo-explainers/flywheel-receipt-demo.html)
walks through one coding task through Flywheel's receipt path: the receipt written, re-derived in a fresh process to MATCH, then forged and caught as DRIFT. Every value on it is output from this repository. Its
source is [docs/explainer/index.html](docs/explainer/index.html).

## Watch

[![Re-derive it. Don't take it on trust.: a narrated film, 2 min 5 s](https://harperz9.github.io/media/explainers/rederive/poster.jpg)](https://harperz9.github.io/explainers.html#rederive-h)

**[Re-derive it. Don't take it on trust.](https://harperz9.github.io/explainers.html#rederive-h)** (2 min 5 s, narrated, captioned). The demo re-derives a receipt in a separate process and catches a forged one, the practice this film describes. The film page carries the transcript, the sources and recall questions.

## Walkthrough

Install it, run it once, then use the main feature. Each command below is real, and so is its output.

1. **Install.** Install the engine from PyPI and clone the demo. Python 3.11 or newer.

   ```text
   $ pip install flywheel-verify pytest
   $ git clone https://github.com/HarperZ9/flywheel-receipt-demo && cd flywheel-receipt-demo/demo
   ```

2. **First run: the demo.** Run a task, write its receipt, re-derive it, then forge it and re-derive again.

   ```text
   $ python run_demo.py
     RESULT: receipt path verified. Honest MATCH, forged DRIFT.
   ```

3. **Re-derive the receipt yourself.** Verify the receipt in a fresh process from the task files beside it.

   ```text
   $ python -m harness.verify_receipt --receipt out/receipt.json --task-dir task
   claimed     verdict PASS, output_hash a2e1d126b3cd1870
   recomputed  verdict PASS, output_hash a2e1d126b3cd1870
   checks      output_hash_matches true, verdict_matches true
   ```

## What is here

- `demo/` is the one-command demo and its own README.
- `FLYWHEEL-TOOLS-EXPLAINED.md` walks the verification model and every lane, with
  each claim pointed at the file in the code that backs it.
- `diagrams/` holds the Flywheel schematics from the main repository: the receipt
  lifecycle, the one-surface architecture, the verified loop, and the capability
  check.
- `INTEGRATION.md` is the five-point brief for binding a hardware attestation quote
  into a Flywheel proof envelope.

## The receipt path, end to end

<p align="center"><img src="diagrams/run-lifecycle.svg" alt="Eight stages from task to offline recheck, with a refusal path back to the tool request, ending in match, changed or unverifiable." width="100%"></p>

<p align="center"><img src="diagrams/architecture.svg" alt="The browser shell, the command line, curl and MCP clients all reach one gateway on localhost, which routes to a local model or an external check and writes a receipt either way, escalating only what does not pass." width="100%"></p>

## The two layers

Hardware attestation proves what ran. A model image and code path executed in
sealed hardware, verifiable through the vendor's attestation service. It cannot
tell you the output was any good, because a sealed enclave can run exactly as
attested and still return a confident wrong answer.

A Flywheel receipt proves the answer re-derives. A skeptic re-runs the recorded
check offline and reaches the same verdict, with no model deciding what passes.
Together they cover both halves, and neither party has to be trusted.

## Honest state

On the shipped benchmark, the verified loop shows no accuracy gain over
single-shot. No capability uplift is claimed. The demonstrated value today is the
re-derivable receipt and the containment: model-written code runs inside an
allowlisted, kill-on-timeout sandbox. The binding with attested inference is a
proposal, not shipped work. `FLYWHEEL-TOOLS-EXPLAINED.md` states what stands where.

## License

Source-available under the Functional Source License (FSL-1.1-MIT). See `LICENSE`.
The engine installs from PyPI as `flywheel-verify`, and the source is at
github.com/HarperZ9/flywheel.
