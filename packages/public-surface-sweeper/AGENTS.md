# AGENTS.md - Public Surface Sweeper

## Scope

This repository is a public Python package and CLI for checking basic public
repository release hygiene.

Use this file for work in this repo. Hygiene rules are stated here so they travel
with the repo when it is cloned on its own: never commit secrets, `.env` files,
tokens, or private corpus or operational material to this public repository.

## Product Boundary

`public-surface-sweeper` may include:

- deterministic public-surface checks in `src/public_surface_sweeper/`,
- CLI output for text, JSON, summary, and proof-packet modes,
- public-safe clean fixtures under `examples/clean-repo/`,
- tests, README material, release notes, and packaging metadata.

It must not include:

- private repository contents, customer data, target data, or proprietary
  corpus material,
- credentials, tokens, `.env` values, browser profiles, or local vault data,
- claims that the tool certifies a repository as secure, compliant, or safe,
- network fetching or live credential validation unless added as a separately
  tested public feature.

The tool surfaces release-hygiene findings. It is not a full security scanner
or certification authority.

## Repo Map

- `src/public_surface_sweeper/sweeper.py` - scan rules, finding formatting,
  summaries, and proof-packet generation.
- `src/public_surface_sweeper/cli.py` - command-line interface and exit-code
  behavior.
- `src/public_surface_sweeper/packet.py` - proof-surface packet validation.
- `tests/test_sweeper.py` - regression tests for required files, text hygiene,
  token-shaped findings, and binary skipping.
- `examples/clean-repo/` - public-safe fixture expected to produce no findings.

## Development

Install locally:

```bash
python -m pip install -e ".[test]"
```

Run the test slice:

```bash
python -m pytest -q
```

Run CLI smoke checks:

```powershell
$env:PYTHONPATH = "src"
python -m public_surface_sweeper examples/clean-repo
python -m public_surface_sweeper examples/clean-repo --summary
python -m public_surface_sweeper examples/clean-repo --proof-packet
```

Run metadata checks before committing:

```bash
git diff --check
```

Before publishing, scan changed files for credential-like values. Do not commit
`.env` files or generated caches.

## Change Rules

- Keep scanning deterministic and dependency-light.
- Keep fixture expectations aligned with CLI output and exit codes.
- Update tests when required files, secret-shaped patterns, summary scoring,
  proof-packet shape, or skip rules change.
- Keep examples public-safe and small enough for release-hygiene testing.
- Document limitations plainly: this tool surfaces public-release defects; it
  does not certify repository safety.
