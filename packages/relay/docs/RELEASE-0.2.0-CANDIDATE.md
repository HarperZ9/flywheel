# Relay 0.2.0 release candidate

Status: candidate until the release owner commits this tree, tags it, builds
artifacts from that commit, verifies download-back hashes, and publishes a
GitHub Release.

## Version decision

Observed release history on 2026-09-08:

- `git ls-remote --tags origin` returned no remote tags.
- `gh release list --repo HarperZ9/relay --limit 30` returned no releases.
- `https://api.github.com/repos/HarperZ9/relay/releases?per_page=30` returned
  no releases.

The repository source declared `0.1.0` before this candidate, but no HarperZ9
Relay tag or GitHub Release was found. This candidate uses `0.2.0` because it
adds a public MCP run/start contract: route dials, acceptance-check dials,
immutable request bindings, durable background result binding, and witnessed
route projection. That is user-visible feature work, not only a patch fix.

The candidate tag should be `v0.2.0` unless the release owner chooses a
different repository tag convention before publication.

## Release boundary

This is a GitHub-only release candidate. Do not publish to PyPI under
`relay-agent`, and do not recommend `pip install relay-agent`. The public PyPI
namespace is not the HarperZ9 Relay distribution.

Candidate install paths are documented in
[`docs/GITHUB-ONLY-INSTALL.md`](GITHUB-ONLY-INSTALL.md). Replace all placeholders
with the accepted commit, release asset URLs, and download-back SHA-256 values
after the release owner publishes artifacts.

## Candidate build commands

Run from the accepted commit:

```bash
python -m pytest -q
python -m build --no-isolation
python -m venv <temp-venv>
<temp-venv>/bin/pip install --no-index --find-links dist relay-agent==0.2.0
<temp-venv>/bin/relay --help
```

On Windows, use `<temp-venv>\\Scripts\\pip.exe` and
`<temp-venv>\\Scripts\\relay.exe`.

## Expected acceptance controls

- `local_agent_run` and `local_agent_start` expose and pass the CLI-backed
  route/acceptance dials.
- Request bindings report effective authority, including `allow_exec` implying
  `allow_write`, while retaining the raw requested gate fields.
- Write denial leaves files unchanged.
- Exec denial prevents `test_cmd` execution.
- Failed checks cannot be accepted.
- Unsupported backends return typed `UNSUPPORTED_BACKEND`.
- Wrong scalar types return typed `INVALID_ARGUMENT`.
- Background run bindings survive status/result/list and restart reload.
- A done result is not visible before the final result record is durable.
- Observed route is the last witnessed assistant route, bounded to ledger
  evidence.
