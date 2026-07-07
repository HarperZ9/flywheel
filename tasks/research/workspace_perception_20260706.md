# The workspace, the transpiler, and giving a model perception it lacks

> Primary source: "Verbalizable Representations as Global Workspace in Language
> Models", transformer-circuits.pub/2026/workspace (fetched 2026-07-06). Captured
> because it is the measurable, internal counterpart to what `harness/boot.py`
> already builds externally, and it grounds the operator's perception thesis.

## What the paper establishes (measurable, falsifiable)

An LLM maintains a privileged subset of representations — a **global workspace**
— where reasoning becomes flexibly usable across downstream processes. Made
measurable via the **Jacobian Lens (J-lens)**: the average linearized causal
effect of a layer-l activation on the final prediction, isolating what each
activation is "poised to speak about". The **J-space** these vectors span is:
- **sparse** (~10-25 vectors active at once), <=10% of activation variance;
- **mid-layer** (meaningful only ~L38-92 of 100);
- **ignition-thresholded** — smooth interpolation early, then a sharp categorical
  commitment at ~L38 (a real onset, not proportional mixing);
- **broadcast-shaped** — J-lens vectors compose with downstream weights far more
  than other directions.

Falsifiers that fire: ablating the top-10 J directions collapses multi-hop
reasoning to near-zero while sparing extractive QA / sentiment / continuation
(same information present; only causal routing removed). Swapping a J-space
component changes the answer (~59% vs ~5% for the non-J component). Unverbalized
intermediate concepts appear in J-lens BEFORE the answer (spider->ant flips 8->6).

## The connection to what we already built

The harness's **boot packet (`boot.py`) is the EXTERNAL global workspace**: the
minimum-token, content-sealed subset gated into the prompt so many downstream
steps can read one shared, re-checkable ground truth. The paper describes the
**INTERNAL** one (J-space). Same shape — a small, broadcast, selectively-required
subset — on two sides of the context boundary. That is not a metaphor: both are
"post a small subset to a shared space many readers consume", and both are
measured by causal effect on downstream behavior, not by presence.

## The perception thesis, made concrete (the operator's direction)

A text model has no native perception of art, color, sound. The **transpiler
(`transpile.py`) gives it perception it otherwise lacks** by encoding a non-text
signal into a carrier the model CAN read, conserving the task-relevant CRITERION
(transpile-conservation), witnessed externally. The workspace paper supplies the
missing measurable target: perception has landed only if the transpiled signal
becomes **workspace-loaded** — usable FLEXIBLY across functions, not just
copied. So the honest test of "we gave the model perception" is not "it echoed
the pixels" but "the transpiled signal shows the workspace signatures: it drives
multi-hop use, survives as an intermediate concept, and its ablation removes the
capability while sparing rote tasks."

**This is the shared layer the operator names:** a native translation where
information becomes both something a model can *see* (transpiled into the readable
carrier) and something two minds can *share* (the same sealed carrier is
re-checkable by human and model). Art / color / sound / philosophy are real
transpilable criteria — each is a lossy transform that must conserve its own
invariant (a palette's relations, a waveform's envelope, an argument's entailment
structure), witnessed, not its bytes.

## Falsifiable next step (buildable, honest)

A **perception-lands-in-the-workspace** test: transpile a signal S (start with
the existing grid/color/sound encoders), give the model a task that requires
FLEXIBLE use of S (multi-hop, cross-function), and measure lift vs a
non-transpiled control. If transpiled-S raises flexible-task accuracy while
leaving rote extraction unchanged, the transpiler is delivering perception, not
decoration. If it only helps rote copy, it is decoration — and we say so. This is
the transpile-conservation principle with the workspace as its external witness.

## Honest scope

- The J-lens is the paper's tool, run on models we do not instrument here; we do
  not have J-lens access to our served 14B. The BEHAVIORAL workspace signatures
  (flexible-use lift, ablation specificity) ARE testable with our harness; the
  INTERNAL J-space measurement is not, without interpretability tooling.
- "Perception" here is criterion-relative and externally witnessed, never a claim
  of subjective experience.
