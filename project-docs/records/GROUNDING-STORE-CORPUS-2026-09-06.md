# A false-accept gate for the layer that holds receipts

2026-09-06. Branch `feat/grounding-signatures-20260906`, continuing the work in
`GROUNDING-FRESH-ENVIRONMENT-2026-09-06.md` and `GROUNDING-SIGNATURES-2026-09-06.md`.

## The axis was scoring one layer

`accountability_bench` publishes an adversarial-soundness dimension. It read
`1.0 - false_accept_rate` from `adversarial_corpus.run_corpus(transitive_verdicts)`,
and `transitive_verdicts` is a pure function over `DepNode` graphs assembled in
memory. That corpus never writes a file and never opens one.

Every attack closed on the resolution path this month sits below that line: an
edit in place, a rewrite refiled under its own new hash, a citation pin that two
citers disagree about, a whole-cone rewrite, a sidecar lifted from another
receipt, an ancestor carrying no signature while signatures are required. Each
has a behavioural test. None of them reached the score. Delete `_load_intact`
and the published axis still reads 1.0, because the layer it measures does not
load receipts.

That is the failure mode the workspace rule calls checking the checks. A
passing verifier that cannot observe the thing it is named after is worse than
no verifier, since it also carries a number.

## What was built

`harness/grounding_corpus_stores.py` holds eleven builders. Each writes real
receipts into a real directory and returns what a caller would hand
`resolve_ancestors`: the sources, the pins those citations carry, the trusted
keys if any, and which node is under test. Eight are attacks whose target must
refuse to resolve. Three are controls whose target must resolve.

`harness/grounding_corpus.py` holds the registry, the runner, and the report.
`run_corpus(resolver_fn)` takes anything with the signature of
`resolve_ancestors`, so the real resolver and every weakened one are scored by
the same code.

No oracle runs anywhere in it. Resolution runs no oracle either, so a receipt
is constructed and filed directly rather than produced by `run_loop` against a
`PytestOracle` at roughly 0.8 s each. That is what keeps the corpus cheap
enough to live inside a benchmark dimension.

## Why the weakened resolvers carry their own walk

A corpus of attacks proves nothing on its own. If a deliberately broken
resolver also scored zero false accepts, the attacks would be scenery, so
`harness/grounding_corpus_strawmen.py` supplies six resolvers that are each
wrong in one named way.

The obvious implementation is an injection seam in `grounding.py`, with the
strawmen passing a weakened node check into the real walk. That would hide a
bug in the walk from its own strawman, since both would inherit it. The
strawmen carry a copy of the walk instead. What keeps the copy honest is the
control set: a strawman that over-rejects a clean store gets reported, and a
broken copy would.

## What each weakened resolver lets through

| resolver | what it removes | attacks it false-accepts |
| --- | --- | --- |
| `no_intactness` | a receipt need not hash to its filename | `edited_in_place` |
| `no_pin` | citation digests are discarded | `refiled_rewrite`, `pin_fork` |
| `sidecar_hash` | discipline 1: the signed hash is read from the sidecar | `whole_cone_rewrite` |
| `sidecar_key` | discipline 2: the sidecar names the authoritative key | `sidecar_names_the_trusted_key` |
| `sidecar_only` | the signed message is rebuilt from sidecar fields | `whole_cone_rewrite`, `lifted_signature` |
| `optional_sig` | discipline 4: a missing sidecar is nothing to check | `unsigned_ancestor` |

None of the six over-rejects a control. That is the result which says the
copied walk is not quietly broken.

`blind_reuse` sits outside that set. It is not one discipline removed but all
of them, a resolver that reuses whatever the store happens to hold under a task
id, and it exists because `score_strawman` needs a store-layer analogue.

## The one attack nothing can fail

`absent_ancestor` cites a receipt that was never written. Every resolver here
refuses it, including the broken ones, because there is no file to load and
nothing to substitute. It measures the builders rather than the resolver.

It is kept for that reason, and the limit is asserted rather than left in a
comment: `test_absent_ancestor_is_the_one_attack_no_strawman_can_fail` computes
the set of attacks no strawman fails and requires it to be exactly that one. A
builder that quietly stopped writing receipts would turn other attacks into the
same shape, and that test would fail.

## The signer is optional and its absence is named

Four stores need a real signature. The harness declares no runtime
dependencies, and that is load-bearing, so `default_signer()` tries
`cryptography`, falls back to PyNaCl, and returns `None` when neither is
installed. Both imports live inside the function, asserted by a test that parses
the module and checks its top-level imports.

When there is no signer those four are named in `skipped` and leave the
denominator. A short corpus reporting as a clean one is the exact failure this
work is about, so `gate_report` says how many were skipped and the runner
records the reason per attack.

One more control guards the signer itself. A signer returning the wrong bytes,
a `SignedMessage` instead of a 64-byte signature for instance, would make every
signed attack refuse for a reason unrelated to the check, and the corpus would
read as sound. `test_the_signer_produces_a_signature_the_stdlib_verifier_accepts`
verifies its output with `harness/ed25519_verify.py` and also checks that the
same signature fails under a different task id.

## Numbers

The axis, before and after:

```
                        attacks  layers  score
before                        7       1    1.0
after                        15       2    1.0
```

The score did not move, which is the correct outcome and also the reason the
detail string now carries the denominator: `0 false-accepts over 15 attacks
(7 closure, 8 store)`. A reader can see which layers were scored instead of
inferring it.

The credibility test moved. `score_strawman` models an unaccountable system and
has to score near zero or the benchmark measures nothing. Its adversarial axis
was 0.0 against the closure corpus alone. Pooled across both layers, with
`blind_reuse` standing in on the store side, it is 0.067, because
`absent_ancestor` is unfailable and sits in the denominator. Benchmark overall
for the strawman goes from 0.0 to 0.01, and the `overall < 0.2` credibility
assertion still holds.

Scoring the strawman on one layer while scoring the benchmark on two would have
been checking a different axis than the one published, so both were changed
together.

Cost, on one Windows machine, `cryptography` present:

```
store corpus, real resolver, 11 stores    0.035 s median of 3, after a warm run
tests/test_grounding_corpus.py, 21 tests  0.61 s
```

The corpus builds and tears down eleven temporary directories in that time. It
is cheap because no oracle runs, which is the reason it can sit inside a
benchmark dimension instead of behind a marker.

## What this does not establish

A clean score says the resolver refuses eight attacks somebody wrote down. It
says nothing about attacks nobody has written, and the value of the corpus is
bounded by the imagination that produced it.

The layer under test is resolution. An accepted ancestor still has to be
re-witnessed, and this corpus does not exercise that path at all.

The signer is generated fresh for each run and thrown away. Nothing here
measures key storage, key distribution, or what happens when a signing key
leaks, which the signature record already names as the boundary it does not
defend.
