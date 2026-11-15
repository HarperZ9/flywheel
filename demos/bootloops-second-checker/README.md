<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/bootloops-second-checker/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/bootloops-second-checker/main/docs/art/hero-light.svg" alt="bootloops-second-checker: Independent second checker for BootLoops RECEIPT v1.0 witnesses. A chain of small linked squares, each holding a few ruled lines, winds inward to a bright core." width="100%">
</picture>

# bootloops-second-checker

Independent second checker for BootLoops RECEIPT v1.0 witnesses.

```
sh scripts/run_all.sh OUT_DIR
```

[![license](https://img.shields.io/badge/license-MIT-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/bootloops-second-checker/blob/main/LICENSE)

An independent second checker for BootLoops RECEIPT v1.0 witnesses, a Lean 4
kernel check of the same identity over `ZMod p`, and a replay of one published
numerical check. MIT licensed.

One witness certifies one reduction-table row at one (kinematic point, prime):

```
sum_i lam[i] * R_i  ==  e_t  -  sum_m c[m] * e_m      (mod p)
```

This repository asks whether that contract can be checked by code that shares
nothing with BootLoops' `core.py`, and whether the two checkers agree.

## Run everything

```sh
sh scripts/run_all.sh OUT_DIR
```

It clones BootLoops at the pinned commit, builds the witness corpus, runs the
three checkers side by side, runs the controls and the spec-edge probe,
replays the sunrise check, runs the Lean legs, and writes `OUT_DIR/SUMMARY.json`
with `OUT_DIR/SHA256SUMS`. `SKIP_LEAN=1` skips the Lean legs, which download
Mathlib (several GB).

## What is here

| path | what it does |
|---|---|
| `src/second_checker/checker.py` | clean-room Python checker, written from `WITNESS_FORMAT.md` only |
| `js/check.mjs` | a second clean-room checker in JavaScript with BigInt arithmetic |
| `src/second_checker/synth.py` | an independent witness generator (Gauss-Jordan with a tracked transform) |
| `src/second_checker/lean_emit.py` | writes each identity as Lean 4 theorems over `ZMod p` |
| `scripts/gen_corpus.py` | builds the witness corpus with BootLoops' own emitters and the generator above |
| `scripts/compare.py` | row-by-row verdicts from both clean-room checkers and `core.py` |
| `scripts/controls.py` | seeded corruptions, the wrong-table class, shuffle controls, dummy checkers |
| `scripts/edge_cases.py` | inputs where the spec is silent or the two readings differ |
| `scripts/lean_run.py` | kernel check of a sample, Lean negative controls, scale limits |
| `scripts/sunrise_quadrature.py` | a 30-digit Feynman-parameter check of one sunrise value |
| `third_checker/` | checkers written by other model families from the spec and tool page only, with their prompts and raw responses; `build_task.py` rebuilds the exact prompt |
| `scripts/compare_third.py` | runs the model-written checkers over the whole corpus |
| `scripts/fuzz.py`, `scripts/fuzz_cases.py` | seeded differential fuzzer over the witness format, with minimized repros |
| `lean/ReceiptLean/Reflect.lean` | proof by reflection: a verified column checker the kernel evaluates |
| `scripts/lean_reflect.py` | kernel check of the corpus by reflection, with a statement-fixed axiom audit and planted controls |
| `EXTENSION-DECISION.md` | what each extension was meant to change, written before the work |
| `REPORT.md` | results, disagreements and limits |
| `.provenance.log` | when the spec, the docs and `core.py` were first opened |

## Third-party material

BootLoops code is not copied here; `run_all.sh` clones it at the pinned commit
and checks the hashes in `inputs/`. The sunrise bundle is downloaded from
bootloops.ai and checked the same way. `third_checker/spec_WITNESS_FORMAT.md` is
BootLoops' `WITNESS_FORMAT.md`, CC BY 4.0, credited in `third_checker/NOTICE`.
The text of the public receipt tool page was part of the model prompt but is
not redistributed, because the page states no license; `third_checker/NOTICE`
says how to fetch it and rebuild the prompt.

## Limits

A mod-p witness certifies one row at one point and one prime. This repository
says nothing about rational reconstruction, the analytic result, or the
physics. See `REPORT.md`, section "What this does not prove".
