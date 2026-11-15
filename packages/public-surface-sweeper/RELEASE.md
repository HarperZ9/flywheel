# public-surface-sweeper v0.1.3

## Release Type

Patch release candidate for workspace Git metadata coverage in the public and
developer delivery matrix.

## User-visible changes

- Recognizes linked Git worktree `.git` files after validating their
  backpointer and common-dir relationship.
- Reports explicit workspace coverage status for empty, local-only, and
  unreadable Git metadata instead of allowing an empty zero-repository matrix
  to pass as clean.
- Rejects symlinked `.git` markers and arbitrary external `gitdir:` targets as
  `UNVERIFIABLE` before reading remote config.

## Boundary

This release surfaces public-release hygiene and local Git metadata drift. It
does not certify repository safety, validate credentials, call the network, or
replace a security review.

## Verification

- `python -m pytest -q`
- `python -m build`
- `python -m twine check dist/*`
- fresh virtualenv install from built wheel
- `public-surface-sweeper examples/clean-repo`
- `public-surface-sweeper examples/clean-repo --proof-packet`
- workspace-mode smoke checks for GitHub worktree discovery and empty
  workspace failure
- `git diff --check`

## Artifacts

- `public_surface_sweeper-0.1.3-py3-none-any.whl`
- `public_surface_sweeper-0.1.3.tar.gz`

## Publishing Notes

GitHub Release artifacts are in scope. PyPI or any other package-registry
publication remains separate and requires registry ownership and credentials.
