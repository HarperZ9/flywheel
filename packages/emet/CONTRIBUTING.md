# Contributing to EMET

EMET is a re-derivability-based integrity verifier. Its value is that every verdict it
emits can be reproduced, and that it refuses to become an authority. Contributions are
welcome - within the boundaries below, which are not negotiable.

## The boundaries a change must respect

A pull request must not make EMET:

- emit a verdict outside the closed lattice `MATCH | DRIFT | UNVERIFIABLE` (in
  particular, never `TRUSTED`);
- adjudicate a model's safety or content decision;
- run inside, or depend on being hosted by, the system it audits;
- enforce, block, sign, or actuate of its own accord;
- depend on a secret or a held key, or on any claim it cannot re-derive.

A change that bends one of these is out of scope no matter how useful. See
[SPEC.md](SPEC.md) section 6.

## Running the checks

```sh
python test_membrane.py                  # behavior proof (23 tests)
python conformance/run.py membrane.py    # reference conformance (40/40)
python membrane.py selftest              # self-hash
```

Both implementations must pass the conformance vectors. If a change alters behavior,
update [SPEC.md](SPEC.md) and `conformance/vectors.json` **together** - the spec is
normative, and the vectors are how an independent implementation reproduces it.

## The most valuable contribution: another implementation

An **independent implementation written against `SPEC.md` alone** (not by reading
existing code), in any language, is the highest-leverage contribution. When it passes
`conformance/vectors.json`, re-derivability gains another witness - and a
*different-author* witness is exactly what the project still needs. Where your
implementation and the spec disagree, **fix the spec**: those divergences are the point.

## Markers and the corpus

The marker denylist is a known-signature set, not a proof of completeness (SPEC sections
8, 11, 16). A proposed marker is data: include the signature, a rationale, and a test
input with its expected count. Absence of a marker is never absence of injection.

## Security issues

See [SECURITY.md](SECURITY.md). Do not open a public issue for an unfixed vulnerability.

## Provenance of authorship

Parts of this project were developed with AI assistance and are committed with
`Co-Authored-By` trailers. Contributions are accepted under the project license
([AGPL-3.0-only](LICENSE)).
