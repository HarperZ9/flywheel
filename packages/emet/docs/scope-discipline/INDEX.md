# Scope Discipline -- Index

This is the reading-order index for the EMET scope-discipline curation: the
operable rubric a maintainer runs on every pull request to answer one question --
**will this change keep EMET an EMET, or quietly turn it into a different
artifact wearing EMET's name?** Each essay is a *re-derivation* grounded in a
[SPEC.md](../../SPEC.md) §6 boundary and the [CONTRIBUTING.md](../../CONTRIBUTING.md)
non-negotiables, never a warrant you must accept on this document's authority. If
an essay and `SPEC.md` disagree, **SPEC governs and the essay is wrong.**

Entry point: [scope-discipline.md](../scope-discipline.md) (the spine -- the
is/ought frame, the full six-gate litmus, the governed verdict set, the worked
edge cases, and the refuter). This file expands the spine into a reading order
and a per-gate map.

## Reading order

- [Depth versus width](./depth-vs-width.md): the is-axis (depth -- re-derivability, coverage, evidence, spec rigor; unbounded growth) versus the ought-axis (authority, adjudication, inside position, enforcement, held key, target actuation; disqualifying), and why usefulness and cost do not net.
- The six gates G1–G6 -- [G1](./G1-re-derivable.md) · [G2](./G2-closed-lattice.md) · [G3](./G3-outside.md) · [G4](./G4-advisory.md) · [G5](./G5-minimal-core.md) · [G6](./G6-no-adjudication.md): the litmus -- every change runs all six, any NO is scope creep no matter how useful, and the six are segments of one perimeter (see the gate map below for each gate's boundary and essay).
- [Over-minimalism](./over-minimalism.md): the symmetric risk -- purity-as-uselessness, where the rubric governs the seam not a freeze, and refusing depth (the JSON envelope, coverage, a second implementation) disqualifies EMET along the is-axis the way creep does along the ought-axis.
- [Fix the spec, not the code](./fix-the-spec.md): when a gate blocks a needed capability the gate is evidence about the spec -- amend `SPEC.md` and `conformance/vectors.json` together, never route around a gate by slipping in an unsanctioned token, write, or dependency.

## The six-gate map

The six segments of the one perimeter, each grounded in a specific SPEC §6
boundary. A NO on any gate is scope creep until the change is reshaped to a YES
or moved to a separate package; the gates are not weighted and do not trade off.

| Gate | Boundary | Essay |
|---|---|---|
| G1 -- Re-derivable: no secret, no held key, no clock | SPEC §6.5 (re-derivable), §8 | [G1-re-derivable.md](./G1-re-derivable.md) |
| G2 -- Stays in the closed lattice: emits no authority, permission, or score | SPEC §6.1 (facts, not authority), §2 | [G2-closed-lattice.md](./G2-closed-lattice.md) |
| G3 -- Outside the audited system | SPEC §6.3 (outside, never inside) | [G3-outside.md](./G3-outside.md) |
| G4 -- Advisory: zero actuation on the target | SPEC §6.4 (advisory), §6.6 (zero actuation) | [G4-advisory.md](./G4-advisory.md) |
| G5 -- Named-core stays stdlib-only; integrations in separate packages | SPEC §10 (Trusted Computing Base) | [G5-minimal-core.md](./G5-minimal-core.md) |
| G6 -- Takes no model-safety or content decision as input | SPEC §6.2 (attests, never adjudicates) | [G6-no-adjudication.md](./G6-no-adjudication.md) |

## Reference and apparatus

- [scope-discipline.md](../scope-discipline.md) §3: the governed verdict set the
  gates enforce -- the closed set EMET may emit (none of which is, or maps to,
  `TRUSTED`), including the monitor tokens newly enumerated as governed.
- [scope-discipline.md](../scope-discipline.md) §4: the worked edge cases sorted
  into DEPTH (ship it) and CREEP (refuse it), each justified by the gate it turns
  on.

*Further reading (lineage and grounding, never warrant):
[SPEC.md](../../SPEC.md) §§2, 5, 6, 8, 10, 11, 13, 14, 16;
[CONTRIBUTING.md](../../CONTRIBUTING.md); [THREAT-MODEL.md](../../THREAT-MODEL.md).
Rationale siblings: [is/ought seam](../rationale/01-is-ought-seam.md),
[spoken-for](../rationale/04-spoken-for.md), [aleph](../rationale/06-aleph.md),
[orientation](../rationale/00-orientation.md).*
