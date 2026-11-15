# The Aperture — Vision Arm Report

> The one untested claim of the thesis: does **shared seeing** (a rendered shape perceived by a
> multimodal model) beat **reconciliation through text** at synthesis? Run 2026-06-23, blind-subagent
> harness. Verdict: **in this run, seeing UNDERPERFORMED reading — and the mechanism is instructive.**

---

## Design (channel held to one variable)

The prior text experiment (`context-experiment/v2-REPORT.md`) found the **relations-only** arm — the bare
relational graph (feed-edges + role labels + flags) as text — matched/beat everything; flat prose was the
floor. The vision arm holds *content* constant and flips only the *channel*:

- **Shared by both arms:** the 109-project inventory as text (109 descriptions can't be rendered legibly,
  so this stays text everywhere — not the variable under test).
- **Arm R (text):** + the relational block as **text** (`arm-R-relations.txt`, the prior winner).
- **Arm V (visual):** + the *same* relational block as a **node-link diagram image** (`ecosystem-graph.png`,
  rendered natively with PIL — no graphviz, no Playwright), with the text relations removed.

Subjects: 4 fresh-context subagents (2 per arm), same model, **blind** to the experiment and to each other.
Judges: 2, **blind to arm** (sets shuffled to neutral labels A–D), one default-model + one Haiku
(cross-model robustness, as in the prior round). Scored 0–3 per question, grounded against the corpus.
Questions: the same S1–S5 synthesis set. The harness used real multimodal perception (each visual subject
read the PNG); no self-perception by the orchestrator (that would be contaminated — the forbidden path).

## Results

Decoded (A=text, B=visual, C=text, D=visual):

| | A·text | B·visual | C·text | D·visual | **text avg** | **visual avg** |
|---|---|---|---|---|---|---|
| Judge 1 (default) | 15 | 10 | 13 | 10 | **14.0** | **10.0** |
| Judge 2 (Haiku)   | 13 |  8 |  9 |  6 | **11.0** | **7.0** |

**Both judges, independently and blind, ranked every text subject above every visual subject** — an
identical **+4.0** text advantage in each. The signal is consistent across judge models, so it is not a
single-judge artifact. Direction is the **opposite** of the thesis's optimistic prediction.

## Mechanism (the instructive part — both judges converged on it)

The gap was driven by **S2** ("which single project's removal most degrades the *whole* system" —
ground-truth: `coherence-membrane`, the afferent convergence node every reconcile flows through):

- **Both text subjects answered S2 correctly** (`coherence-membrane`), reasoning by *counting convergence*
  from the explicit edge list (`raw -> coherence-membrane`, `studio-engine -> coherence-membrane`,
  `accountable-surface -> coherence-membrane`, and it heads the spine chain).
- **Both visual subjects answered S2 wrong** (`accountable-surface`) and **shared a hallucination** — "the
  only node with a *bidirectional edge* to proof-surface AND emet." Judge 1 scored these 1, Judge 2 scored
  them 0.

Why the visual channel produced this: the diagram makes **spatial salience** carry weight that the text list
does not. `accountable-surface` sits mid-spine, is the visually central box, and wears the prominent
`FLAGSHIP a` tag — so it *looks* like the hub. And the two genuine directional edges between it and
proof-surface (`A->B` and `B->A`) render as overlapping arrows that *look* like one bidirectional connector,
which the subjects over-generalized into a (false) bidirectional link to emet. The text reader sees a list
and counts; the image reader sees a center and a flag and is pulled to it. **Layout injected a centrality
bias the text representation is immune to.** The arms agreed where the answer was channel-independent (both
found the S3 efferent/actuation gap), and diverged exactly where reading the *shape* could mislead.

## Honest limits (why this is a signal, not a proof)

- **The decisive confound is rendering/layout.** The visual arm's failure is entangled with *my* diagram:
  the accidental bidirectional-looking arrow and the central placement + flagship tag of accountable-surface.
  A neutral layout (e.g., coherence-membrane centered, edges de-duplicated, flags suppressed) might shrink or
  flip the gap. **I cannot separate "vision underperforms" from "this particular diagram misled."** That is
  the core caveat: the result is about *naive rendering*, not about vision-in-principle.
- N=2/arm, single subject model, one corpus, **one diagram**; 2 judges with partial model-family overlap
  with the subjects. Single run.
- The inventory was text in both arms, so this tests "relations-as-picture vs relations-as-text," not
  "fully-visual vs fully-text."

## Verdict

**Shared seeing did not beat shared text here — it lost, consistently across two blind judges, via a
spatial-salience mechanism that produced a shared wrong answer and a shared hallucination on the one
question with a hard ground-truth.** This is **zero evidence for** the shared-seeing-beats-text thesis and
**concrete evidence that** a naively rendered shape can *actively degrade* synthesis by injecting centrality
bias the text graph doesn't carry. It does **not refute** the thesis in principle — the layout confound is
real and a fairer render is the obvious next probe — but the optimistic version ("just render the shape and
the model will understand more") is not supported, and the failure mode is specific and reproducible: **the
picture tells you what to look at; the list makes you count.** The prior result stands sharpened — *encode
the relations and let the model compose*; doing that as a picture adds a salience channel that, untuned,
hurts more than it helps.

## Next probes
1. **Neutral re-render** — de-duplicate bidirectional arrows, drop the flagship tag, center the true
   convergence node; re-run. Does the gap close? (Isolates layout-salience from channel.)
2. **Multi-layout** — 3 layouts of the same graph; if scores swing with layout, salience (not channel) is
   the lever — itself a finding about "the shape" the thesis leans on.
3. **Fully-visual** — render a legible *subset* (the spine + lineage only, no 109-item inventory) and ask
   spine-local questions, so neither arm has a text crutch.

*Artifacts: `render_graph.py`, `ecosystem-graph.png`, `armV-inventory.txt`, `vision-answers/` (4 blind
subject sets + private mapping). Source corpus: `context-experiment/`.*
