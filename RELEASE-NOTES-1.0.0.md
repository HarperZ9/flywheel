# Flywheel 1.0.0

A self-hostable, model-agnostic AI workstation and coding harness. Run a task with any
model, local or frontier, behind one OpenAI-compatible surface (about twenty endpoints:
OpenAI, Anthropic, Gemini, DeepSeek, subscription CLIs, local serve, Ollama). Run a gated
coding agent over your own folders. And get a proof receipt on the result that anyone can
re-run offline.

Its backbone is re-derivable verification, enforced in code: no receipt, no accept, and no
learned model on the accept path. Only a real oracle, a test runner or a data-only
certificate checker, can accept an answer, and each accepted answer emits a proof envelope.
Hand it to the witness and it re-runs the recorded check and recomputes the hash: MATCH,
DRIFT, or UNVERIFIABLE. A third party reproduces the verdict without your machine.

Beyond verification it ships research intake, agent orchestration, code intelligence, an
accountable-learning forge, a memory and continuity substrate, a deterministic creative
studio, gated actuation, governance receipts, and cross-harness bridges (ACP, LSP, DAP, and
a METR Inspect bridge), organized as swappable lanes that compose through published JSON
seams. Full feature set and a walkthrough are in docs/FLYWHEEL-1.0.0-OVERVIEW.md.

## Install

- Engine: pip install flywheel-verify
- Desktop app: the Windows installer (Flywheel-Setup-1.0.0-x64.exe) is attached below.

## Honest state

- Model-agnostic across frontier and all providers plus local. Verification is the
  backbone that the rest of the engine rides on.
- On the shipped benchmark the verified loop shows no measured accuracy uplift over
  single-shot; the interval includes zero. The demonstrated value is the re-derivable
  receipt and the containment, and capability uplift is the direction the mechanisms aim at.
- The internal classifier and encoder are experimental, abstain today, and stay off the
  accept path by design.
- The chorus discourse lane and the compose claim-verification pipeline land in 1.0.1.
- A receipt proves a check reproduces. It does not prove the answer is true of the world.
- This is an independent project, built in the open, with the honest nulls left in.
