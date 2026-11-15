# Reproduce verifiers-component-forge

This environment is a local, synthetic fixture family for writing verifiers
components against terminal-state contracts. It does not contact a model, a
provider, a network service, or a private endpoint during its tests.

## Setup

Run from this directory:

```bash
uv run --python 3.13 --prerelease=allow --with pytest python -m pytest tests/ -q
```

If `uv` selects Python 3.14, force Python 3.13 as shown above. The project pins
its supported Python range to `>=3.11,<3.14` because `verifiers` currently
publishes in that range.

## Regenerate frozen fixtures

```bash
uv run --python 3.13 --prerelease=allow python generation/generate.py
```

The generator builds each frozen JSON file twice in one process and refuses to
write if either build differs. Test coverage then compares the committed files
against fresh regeneration.

## Lint and types

```bash
uvx ruff check verifiers_component_forge generation tests
uvx ruff format --check verifiers_component_forge generation tests
uvx ty check --python <venv-with-verifiers> verifiers_component_forge generation
```

All three pass clean. `ty` needs `--python` pointed at an environment with
verifiers installed; without it the verifiers imports are unresolvable and
report as diagnostics.

## Live-model eval evidence

The committed `outputs/evals/` runs were produced with `vf-eval` (verifiers
0.3.0) against the Anthropic API: 5 examples (shuffle seed 0) x 3 rollouts
per family, models `claude-haiku-4-5-20251001` and `claude-sonnet-5`,
max_tokens 8192, `ANTHROPIC_API_KEY` in the environment. Each per-family
run is one `[[eval]]` entry in a TOML config passing
`env_args = { families = [...] }` to `load_environment`.

Two Windows-specific notes, needed only when reproducing on Windows:

- vf-eval's default ZMQ env-server binds an `ipc://` socket, which does not
  exist on Windows; set `disable_env_server = true` in the TOML (an
  in-process mode not exposed as a CLI flag). On Linux the default works.
- verifiers 0.3.0 injects an `httpx` client into `AsyncAnthropic`, so the
  anthropic SDK must be `<1.0` (1.0 switched to a vendored httpx2 and
  rejects the injected client).

## Rubric-repair kill-check

The `rubric-repair` family ships only mutants that flip at least two battery
fixtures under the installed verifiers, so one flip is shown as the visible
symptom while at least one stays hidden and scored. The generator refused the
`guard-dropped` operator wholesale: verifiers itself scores a raising reward
function as 0.0, which makes removing the reference's try/except behaviorally
invisible, and a non-discriminating mutant never ships. The frozen file
records a no-op ceiling per instance (0.0 for gate-breaking mutants, the
regression share 0.15 otherwise); tests assert every ceiling and replay a
sample through the real child driver.

```bash
uv run --python 3.13 --prerelease=allow --with pytest python -m pytest tests/test_rubric_repair.py -q
```

## Referee-protocol fold cross-check

The `referee-protocol` family freezes what the real `MultiTurnEnv.rollout`
produces from each reference referee under canned player scripts. An
independent pure fold of the same state machine (no verifiers dependency)
recomputes every frozen row; the generator aborts on any disagreement and
the test suite sweeps all 512 scripts again. Discrimination is pinned
through the real child driver: the reference scores 1.0, overriding
`rollout` (even delegating to `super()`) zeroes on the identity gate, and a
wrong reward schedule earns exactly the transcript-only partial credit.

```bash
uv run --python 3.13 --prerelease=allow --with pytest python -m pytest tests/test_referee_protocol.py -q
```

## Redaction-contract public-safety check

The `redaction-contract` family uses only fake marker values with the prefix
`FAKE_SECRET_DO_NOT_USE_LOOP29`. Raw markers are allowed in synthetic input
fixtures because the scorer needs something to redact. The expected terminal
outputs are scanned by tests and must not contain that prefix.

Relevant tests:

```bash
uv run --python 3.13 --prerelease=allow --with pytest python -m pytest tests/test_redaction_contract.py -q
```

## Does not prove

Passing these tests does not prove upstream maintainer interest, model quality,
production secret handling, sandbox security, legal clearance, or readiness to
publish. The child-process runner is a deterministic scoring boundary, not a
security sandbox. Any public release still needs a fresh public-safety scan,
repository status check, and action-time approval.
