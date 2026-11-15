# Coherence Membrane Usage

## Install For Development

```sh
python -m pip install -e ".[test]"
```

## Run The Core Checks

```sh
python -m pytest
python conformance/run.py
node impl/js/run.js
python -m coherence_membrane selftest
```

## Observe An Artifact

```sh
python -m coherence_membrane selftest
python -m coherence_membrane perceive frame.png
python -m coherence_membrane capture frame.png
python -m coherence_membrane watch 60 --raw
python -m coherence_membrane distill --code --original mod.py --candidate mod_small.py
```

`capture` and `watch` perceive local screen state. Use them only on surfaces the
operator owns or is authorized to inspect. `distill` accepts a compressed
rewrite of a source file only when the declared criterion survives.

## Use From Python

```python
from coherence_membrane import perceive, compare_drift

snapshot = perceive(["frame.png"])
observation = snapshot.observations[0]
verdict = compare_drift(
    observation.data["identity_sha256"],
    observation.data["identity_sha256"],
    observation.data.get("perceptual_hash"),
    observation.data.get("perceptual_hash"),
)
```

The membrane reports observations and drift. A host runtime or separate gate
decides what to do with those facts.

## Public Boundary

- Observations are inert read-side facts.
- Receipts and graph bindings are keyless unless externally anchored.
- Native capture reads composited display output; it does not inject into or
  hook another process.
- Unsupported or unreadable artifacts fail closed to `UNVERIFIABLE` or an
  unverified observation, never to a fabricated match.
