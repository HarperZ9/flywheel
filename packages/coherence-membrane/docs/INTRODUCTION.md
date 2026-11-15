# Introduction to Coherence Membrane

Coherence Membrane is a Python library, built on the standard library alone,
that lets an AI agent, a test harness, or any host program read real local
state. It turns files, PNGs, WAVs, JSON documents, captions, and live screen
frames into structured observations carrying exact SHA-256 identities, measured
dimensions, and 64-bit perceptual fingerprints. It compares those observations
against baselines you pinned and returns one of three verdicts: MATCH, DRIFT,
or UNVERIFIABLE.

Screen capture goes through the OS compositor via `ctypes`, so it works under
D3D, Vulkan, OpenGL, Metal, and software renderers alike.

## Why it exists

A language model reasons on its prior and on source text, not on what actually
happened at runtime. "This frame renders correctly" is, structurally, a guess
dressed as a fact. The membrane replaces the guess with a witnessed,
re-derivable observation the model can ground on, which is the same move twice:
it stops an agent acting on a hallucination, and it finally closes the make,
look, compare, adjust loop the agent was always blind in.

## Core concepts

**Observation.** The unit of perception. Every observation carries the
full-width SHA-256 of the exact bytes it saw, modality-specific facts (width
and height, audio envelope hash, canonical JSON identity, glyph grid), and a
status. When an artifact fails to parse, the observation records that in its
status and leaves its data fields empty.

**Organ.** A single sense with a contract: it reads and reports, leaves
what it reads unchanged, and ships a `selftest()` that re-derives its own
claims from a known artifact. Sixteen organs are registered by default,
covering sight, hearing, structured data, captions, region drift, glyph views,
contours, palettes, raw frames, and six deductive verifiers.
`python -m coherence_membrane selftest` runs them all and exits 1 when an
organ fails its own test.

**Drift lattice.** Every adjudicator returns a verdict from a small closed
set. MATCH requires positive evidence, absence of evidence is UNVERIFIABLE,
and contrary evidence is DRIFT. These laws are not docstrings: `lattice.py`
proves them by exhaustive enumeration on every `pytest` run, including that
composing verdicts can never turn a worse set into a better one.

**Baseline.** Operator-authorized memory. Pin an observation, then check later
observations against it on a three-rung ladder: byte identity, canonical
(normal-form) identity, perceptual distance. A reformatted JSON document is a
MATCH; a changed value is a DRIFT. Baselines persist to disk.

**Continuity.** The always-on loop. A cheap identity hash runs every tick,
and a real change escalates to the full perceptual work. A `ResourceBudget`
caps and paces that work. A change over budget is still reported, as
UNVERIFIABLE("throttled").

**Receipt and provenance.** `emit_receipt` wraps an observation's facts with a
content anchor the operator pins or signs out-of-band; `verify_receipt`
re-derives and checks it. `ProvenanceGraph` chains observations, actions, and
gate decisions into a hash-bound DAG where tampering any surviving node breaks
everything downstream.

**The two gates.** This repo is the read-gate: what is actually there? Its
complement, [proof-surface](https://github.com/HarperZ9/proof-surface), is the
write-gate: may this action proceed? They compose through a shared JSON shape,
not a dependency, so each is useful alone.

## Your first ten minutes

Install from source (Python 3.10 or newer is the one requirement):

```bash
git clone https://github.com/HarperZ9/coherence-membrane
cd coherence-membrane
python -m pip install -e ".[test]"
```

1. Make the membrane prove itself before you trust it:

```bash
python -m coherence_membrane selftest
```

Expect a JSON report with `"passed": true` and 16 entries under
`"results"`, one per organ. The command exits 0 on a pass and 1 on a failure,
so a script can gate on it.

2. Perceive something real. Grab your own screen, then observe the file:

```bash
python -m coherence_membrane capture shot.png
python -m coherence_membrane perceive shot.png
```

The perceive output shows the identity hash, the dimensions, and the
perceptual hash. Run it twice: the identity is bit-stable. Capture surfaces you
own or are authorized to inspect.

3. Detect drift from Python:

```python
from coherence_membrane import perceive, Baseline

obs = perceive(["shot.png"]).observations[0]
b = Baseline()
b.pin(obs)                                   # authorize this state
b.check(obs).verdict                         # MATCH
# edit or re-capture shot.png, then:
b.check(perceive(["shot.png"]).observations[0]).verdict   # DRIFT
```

4. Watch live state change-proportionally:

```bash
python -m coherence_membrane watch 30 --raw
```

One JSON event per frame. Unchanged frames cost an identity hash; a real
change reports a perceptual distance. The `--raw` flag skips PNG encoding
entirely and is the path to use at high rates.

5. Verify a deductive claim instead of trusting an assertion:

```python
from coherence_membrane import PropositionalVerifierOrgan
from coherence_membrane.propositional import Var, And, Implies

A, B = Var("A"), Var("B")
obs = PropositionalVerifierOrgan().observe(Implies(And(A, Implies(A, B)), B))[0]
obs.data["verdict"]   # "verified"
```

An oversized or undecidable claim comes back UNVERIFIABLE, so a verdict of
"verified" always carries a completed check.

## Where to go next

- The [README](../README.md) has the full capability list, the CLI table, and
  the honest-limits section.
- [USAGE.md](../USAGE.md) states the public boundary in five lines.
- [ROADMAP.md](../ROADMAP.md) shows what is planned, and flags the items that
  need a Linux or macOS machine to validate.
- `conformance/run.py` and `impl/js/run.js` re-derive the frozen 16-case
  contract corpus in Python and Node.js respectively; `schemas/` holds the
  JSON Schemas for the wire shapes.
- The test suite (`python -m pytest`, 914 passing) is the most precise
  documentation of behavior, including the machine-checked lattice proofs in
  `tests/test_lattice.py` and `tests/test_lattice_binding.py`.

To re-check any of this yourself, run `python conformance/run.py` and
`node impl/js/run.js`: both re-derive the frozen 16-case corpus, value for
value, from separate code in two languages.
