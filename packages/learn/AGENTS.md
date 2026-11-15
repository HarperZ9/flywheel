# learn Agent Instructions

## Scope

`learn` is the Project Telos accountable credential and coursework engine. Changes should improve
the learning-loop capabilities (spaced repetition, retrieval practice, self-explanation,
misconception targeting, concept mapping, predict-then-observe, study orchestration), the
credential-logistics engine (workflow, runtime, adapters, receipt), or developer ergonomics,
without weakening the integrity floor.

## THE INTEGRITY LINE (load-bearing)

Every learning-aid capability generates practice, structures study, or checks the operator's own
work. It must never produce, hint, or auto-fill an answer to a certified/graded assessment.
Renders and sources are aids. The tutor `mastery()` verdict must remain a function of the
operator's own practice attempts only. Where a change could be misread as crossing this line, add
a falsifiable test proving it does not, and wire it into `doctor.mjs`.

## Developer Contract

- Zero external dependencies. Node >= 20. ES modules (`.mjs`). Tests via `node:test` and
  `node:assert/strict`. Never add a dependency.
- TDD: write the failing test first, confirm it fails, implement minimally, confirm it passes,
  then run the full suite before committing.
- Keep the CLI (`src/cli.mjs`) and MCP (`src/mcp.mjs`) surfaces aligned: a new read/advisory
  capability should be reachable from both where it makes sense. Actuation (real runs against a
  live course) stays operator-driven on the CLI. The MCP server exposes read tools plus two that
  write tutor sessions, and every id and path it takes stays inside the learn state folder
  (`src/state.mjs`).
- Start any child process through `src/interop/spawn.mjs`, which uses the vendored
  `src/_vendor/safe_spawn.mjs`. Never edit the vendored file; `tests/vendored.test.mjs` checks it
  against `VENDORED.sha256`.
- Keep `README.md`, `CHANGELOG.md`, `status.mjs`, and `doctor.mjs` current when behavior changes.
- No file over 300 lines; no function over 50 lines. Split/extract rather than grow a file past
  that.
- Do not add network behavior to the tutor or workflow engines without a receipt shape and a
  testable boundary; the assist/telos interop paths already model this (fail-closed, tagged aid,
  never graded).

## Verification

Run the targeted slice for the touched surface first, then the full suite before committing:

```bash
node --test tests/learn-<touched-area>*.test.mjs   # targeted slice
node --test                                        # full suite, must show 0 fail
node src/cli.mjs status
node src/cli.mjs doctor
```

`doctor` must report `MATCH` before a commit lands. A `FAIL` on any integrity-invariant check
blocks the change until fixed, not until suppressed.

Before a release, check the package as a person gets it, and the release gate:

```bash
npm pack --pack-destination packed
node scripts/smoke-tarball.mjs packed/harperz9-learn-<version>.tgz
node scripts/check-release.mjs v<version> HarperZ9/learn
```

Releases go out only through `.github/workflows/release.yml` on a `v*` tag (npm trusted
publishing). Never publish from a local machine.
