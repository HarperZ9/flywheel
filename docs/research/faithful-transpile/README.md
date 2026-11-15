<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/faithful-transpile/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/faithful-transpile/main/docs/art/hero-light.svg" alt="faithful-transpile: Working paper and experiments on faithfulness across minds. A fan of ruled sheets drawn in fine lines, the top sheet lit by a bright core." width="100%">
</picture>

# faithful-transpile

Working paper and experiments on faithfulness across minds.

```
python sims/<file>.py
```

[![license](https://img.shields.io/badge/license-CC_BY_4.0%2C_MIT-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/faithful-transpile/blob/main/LICENSE)
![python](https://img.shields.io/badge/language-python-e6e1d6?style=flat-square&labelColor=1a1712)

> How a subject crosses between minds, and the neutral center where it finds its form.
> Original work by **Zain Dana Harper**. Text: CC BY 4.0. Code: MIT. Authored and dated 2026-06-23.

A companion to the accountability research at
**[harperz9.github.io](https://harperz9.github.io)**. That work argues accountability can
be an intrinsic, bilateral property; this one asks the question underneath it — *what
actually crosses between two minds, and what makes a shared answer "best"* — and answers it
with falsifiable experiments rather than assertion.

## The thesis, in one breath

Information that crosses a boundary — between two minds, between two substrates, between two
senses — is not conserved as bits. Almost all of the bits can be discarded. What can be
conserved is **faithfulness to a criterion**: the recoverability of a specific readout of
the subject. Faithfulness is **relative to a named criterion**, and it **cannot be certified
from inside** — only against an external one. From this: a **neutral center** where two
differently-perceiving minds render a subject perceptible, reconcile it against an unauthored
criterion, and carry a witness, is how a subject reaches its best form — and *which* criterion
is "best" is an irreducibly human choice. That last fact is not the limit of the idea; it is
what lets one center serve every domain.

## Status — labeled, not inflated

A **working paper**, standing — **not a theorem**. Every claim is tagged
**`[established]` / `[designed]` / `[reach]`** so the earned and the speculative never blur.
The core principle is *established*: it is replicated across ten mechanically-independent
substrates spanning every sense (sight, sound, shape, language, structure, quantity,
identity), with pre-registered falsifiers that did not trigger. The neutral center is
*designed* and live-demonstrated, with its honest boundary shown. The closing reflection on
where thoughts come from is *reach* — fenced as a question, not a claim. Read the labels;
they are load-bearing.

## Where to start

- **`THESIS.md`** — the paper: the principle, the formal statement (Defs. 1–3, Props. 1–5),
  the evidence across the senses, the neutral center, the boundary, and a fenced coda.
- **`PRINCIPLE.md`** — the principle and the per-substrate results in one place.
- **`sims/`** — the ten substrate experiments (Python, stdlib + PIL), deterministic and
  seeded. Each prints its own pre-registered verdict. Run any: `python sims/<file>.py`.
- **`DEMO-two-minds.md`** — the live demonstration of the center (two minds, different senses,
  reconciling a subject), with the criterion-relativity result.
- **`center.py`** — a runnable seed of the center's core interaction: name a criterion, and
  the verdict follows from it, witnessed.
- **`ENDGAME.md`** · **`VERDICT.md`** — the prior simulations the principle grew out of.

## Priority & provenance

`MANIFEST.sha256` is a content-addressed record of every file here — a provable, dated
priority stake so the work is **citable and cannot be quietly appropriated**. Verify with
`sha256sum -c MANIFEST.sha256`.

This is the *research*. Where it names a built system, the buildable implementation and any
internal tooling are not part of this repository; what is published is the work and its
evidence.

## The center, running — `center/`

A runnable seed of the paper's neutral center (v1, stdlib, hermetic). A human authors a **named,
weighted criterion**; a subject is rendered into two perceptible forms; two pluggable minds with
different senses reconcile it (solo → meeting → crystallize); an external judge scores each candidate;
a grounding guardrail penalizes over-build; and a **Certificate naming the criterion** is emitted.
Criterion-relativity is live — the winner *flips* with the named criterion.

```
python -m center reconcile --subject <path> --criterion creator.json     # novelty-weighted → a solo wins
python -m center reconcile --subject <path> --criterion researcher.json   # wholeness-weighted → the meeting wins
python -m center.tests.test_center                                        # 6/6 hermetic tests
```

The minds and judge are **pluggable interfaces** (v1 ships deterministic stubs, no model/network);
the live perception/generation organs drop in behind the same interface. This is the engine's *operation*,
runnable — not the full live engine.

## Licence

Text: CC BY 4.0. Code: MIT.

The thesis and its companion papers (00-ABSTRACT, THESIS, PRINCIPLE, ENDGAME,
VERDICT, DEMO-two-minds and vision-arm-REPORT) are licensed CC BY 4.0. The
published version is deposited at
[doi.org/10.5281/zenodo.23126484](https://doi.org/10.5281/zenodo.23126484) under
the same licence. Share and adapt them with credit to Zain Dana Harper; the terms
are in [`LICENSE-TEXT`](LICENSE-TEXT). The code in `center/` and `sims/` stays
under the MIT terms in [`LICENSE`](LICENSE).

---

*Zain Dana Harper · [harperz9.github.io](https://harperz9.github.io) · Text CC BY 4.0, code MIT · 2026.*
*Proof before trust — including about authorship.*

---

Built by **[Zain Dana Harper](https://harperz9.github.io)** in Seattle: evidence-first tools that leave a re-checkable artifact behind. The full workbench is at [Project Telos](https://harperz9.github.io).
