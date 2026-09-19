# Flywheel 1.0.1

A self-hostable, model-agnostic AI workstation and coding harness. Run a task with any
model, local or frontier, behind one OpenAI-compatible surface (about twenty endpoints:
OpenAI, Anthropic, Gemini, DeepSeek, subscription CLIs, local serve, Ollama). Run a gated
coding agent over your own folders. Get a proof receipt on the result that anyone can re-run
offline.

The backbone is re-derivable verification, enforced in code: no receipt, no accept, and no
learned model on the accept path. Only a real oracle, a test runner or a data-only
certificate checker, can accept an answer. Each accepted answer emits a proof envelope. Hand
it to the witness and it re-runs the recorded check and recomputes the hash for a MATCH,
DRIFT, or UNVERIFIABLE verdict. A third party reproduces the verdict without your machine.

## What 1.0.1 adds

1.0.1 folds the last standalone flagships in as native lanes and documents the whole family.

- The compose pipeline (harness/compose_claim.py) chains three lanes through their JSON
  seams: gather turns sources into a witnessed digest, chorus reads the same corpus into a
  deterministic discourse digest, and crucible adjudicates a falsifiable claim against the
  gather digest for an arithmetic MATCH / DRIFT / UNVERIFIABLE verdict. A bundle binds the
  three stage fingerprints into one receipt a third party re-runs.
- chorus is a native lane: a re-derivable discourse digest of themes, the sharpest dissent,
  and a receipt that recomputes from the raw text.
- articulate is a native lane: a writing-quality and AI-tell detector and editor that can
  carry a content-free audit receipt. Every publication and product surface in this release
  was measured against it.
- A feature-doc tree (docs/features/) documents each former flagship as a native feature.
  Every doc carries a description, a feature list, stepwise use, a piecewise reference, and a
  composition tutorial. The index (docs/features/README.md) shows how the lanes compose.
- A product history (docs/PRODUCT-HISTORY.md) traces the build from EMET on 2026-06-06
  through the engine and its lanes, dated from the repositories themselves.
- The README is model-agnostic across frontier and local providers, with the full lane
  roster and links to the overview and the feature docs.

## Install

- Engine: pip install flywheel-verify
- Desktop app: the Windows installer (Flywheel-Setup-1.0.1-x64.exe) is attached below.

## Honest state

- Model-agnostic across frontier and all providers plus local. Verification is the backbone
  the rest of the engine rides on.
- On the shipped benchmark the verified loop shows no measured accuracy uplift over
  single-shot. The interval includes zero. The demonstrated value is the re-derivable receipt
  and the containment. Capability uplift is the direction the mechanisms aim at.
- The internal classifier and encoder are experimental. They abstain today and stay off the
  accept path by design.
- Every former standalone flagship is now a documented native feature that stands alone and
  composes through published seams.
- A receipt proves a check reproduces. It does not prove the answer is true of the world.
- This is an independent project, built in the open, with the honest nulls left in.
