# Preregistration addendum: the isomorphic-perturbation diagnostic, with corrected transforms

**Addendum to:** `prereg.size-invariant-verification.v1`, frozen sha256
`31055c924d48fe67ebdf29ab8f067840f83ccc6ff1d1f469bc0abb2be0dffa08`.

**Status:** FROZEN when this file's sha256 is appended to the ledger as an
`isomorphic-perturbation-addendum` event. Frozen while the confirmatory walk is
still generating and before any pool outcome is readable: the analysis drivers
refuse to run until the journal carries run_end, so nothing in this design can
have been informed by a result.

**Register:** the `flavored` profile. Calibrated uncertainty is kept.

---

## 1. What this adds

A DIAGNOSTIC arm. Each frozen instance gets a solution-preserving transform,
the transformed instances get their own generation pass into a separate pool
root under the same fingerprint discipline, and the measurement is the paired
per-task gap between original and transformed, per rung, per family. A large
gap is evidence the model's success depends on the surface form of the instance
rather than on the property being asked about. No claim rule promotes this arm
into the primary endpoint, and section 5 says what a small gap does not mean.

## 2. The first design's defects, kept on the record

The roadmap version of this item was blocked with two defects, recorded here so
the correction is visible rather than silent.

- **A category error.** The crossing transform was written as reflect, rotate,
  or affine-map the instance. The instance is an abstract graph and has no
  coordinates: those transforms act on the CANDIDATE'S DRAWING, which is the
  solution space, not the problem. A non-lattice rotation also breaks the
  checker's strict-integer coordinate requirement.
- **A vacuity.** The Zarankiewicz transform was row and column permutation. The
  checker's binding is `(m, n, s, t)`, all four invariant under permutation,
  and the instance's seed witness is not bound at all. A memorized answer to
  the ORIGINAL instance therefore still passes against the permuted one, and
  the measured gap is structurally zero regardless of what the model does.

## 3. The corrected transforms

**Zarankiewicz: TRANSPOSE.** The transformed instance is
`(m, n) -> (n, m)`, with `s, t` unchanged and each seed edge `(i, j) -> (j, i)`.
Solution-preserving because K_{2,2}-freeness and the edge count are symmetric
under transposition: `z(m, n; 2, 2) = z(n, m; 2, 2)`, and a valid certificate
maps to a valid certificate by swapping every edge pair. It has teeth because
the binding's `m` and `n` swap: a memorized original answer declares the old
shape and FAILS the binding check on the transposed instance. No checker
changes, no criterion change. Coverage, measured against the frozen generator
before freezing this document: **60 of 60 instances have m distinct from n**,
so no instance is excluded.

**Crossing: VERTEX RELABELING.** A seeded permutation of `range(n)` is applied
to the instance's edge list, which is then normalized exactly as the checker
normalizes it. The permutation seed is declared here: `20260728`, keyed per
task as `perm:20260728:<task_id>`, Fisher-Yates. A draw is rejected and redrawn
if the relabeled, normalized edge list equals the original (the permutation was
an automorphism of the canonical form); a task where 16 draws all fix the edge
list is EXCLUDED AND NAMED, never silently kept. Solution-preserving because
the relabeled graph is isomorphic and its rectilinear crossing number is
identical; a valid drawing maps by composing the coordinate assignment with
the inverse permutation. It has teeth because the binding is `(n, edges_key)`
and `edges_key` moves with the relabeling. Coverage, measured the same way:
**60 of 60 instances have n of at least 3**, so a non-identity permutation
exists for every task.

## 4. Measurement

- Same K = 4, same seed and temperature schedule, same declared extraction,
  one fingerprint per rung, all inherited from the parent. The transformed
  pools live under their own root and keep the parent's task ids, so original
  and transformed pair by task id.
- Primary quantity: the paired per-task gap on the `single` arm (slot 0,
  temperature 0), McNemar exact on the discordant pairs with the declared MDE
  beside it, per rung, per family, computed by the same drivers behind the
  same run_end gate as everything else.
- The serving surface must be re-witnessed against the determinism pins before
  the transformed pass runs; a pass on a drifted surface pairs nothing.
- Initial execution scope: the 1.5B, 3B, 7B and both 14B rungs. The 0.5B and
  both 32B rungs run as compute allows. A rung whose transformed pass did not
  run is UNVERIFIABLE for this diagnostic, never a null, and never inherits a
  neighbour's gap.

## 5. Does not prove

- **NOT_PROVES_MEMORIZATION.** A gap shows sensitivity to the transform, which
  memorization would produce and which format or tokenization sensitivity
  would also produce. The transform cannot tell those apart.
- **NOT_PROVES_ROBUSTNESS.** A zero gap covers two transforms on two families,
  under one template and one decoding schedule. Robustness in general is a
  universal claim and no finite diagnostic reaches it.
- **NOT_PROVES_THE_PRIMARY_ENDPOINT_EITHER_WAY.** This arm reads the same
  pools and changes nothing about the accept path, the endpoint, or the claim
  rule. It is a lens, not a verdict.
- **NOT_PROVES_TRANSFER.** The ladder is Qwen-dominant with one non-Qwen rung,
  and every confound the parent lists for the secondary tables applies here
  unchanged.

## 6. Cost, stated before it is spent

One additional generation pass over the scoped rungs, both families. The
confirmatory journal's wall seconds are mechanical facts and price the scoped
subset directly; the transformed pass is expected to cost roughly what the
same rungs cost in the confirmatory pass, and the 32B rungs are excluded from
the initial scope precisely because they dominate that price.
