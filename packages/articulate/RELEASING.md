# Releasing Articulate

A release is a version tag on `main` plus a published GitHub release for that
tag. Publishing the release runs `.github/workflows/publish.yml`, which builds the Python package, the Claude
Code plugin and the Windows native package, then publishes to PyPI and attaches
the archives to a GitHub release.

## Version numbers

Articulate uses `MAJOR.MINOR.PATCH`.

- A minor release (`0.14.0`) adds features or changes behavior.
- A patch release (`0.14.1`) ships bug fixes only. It needs no minor release
  first.

Before 0.14.0 the native build refused any version that did not end in `.0`.
That check stopped the 0.12.1 publish at `native-build`. The check is gone. The
release checks below still apply to every version, patch or minor.

## What the release checks hold

`scripts/native_release_source.py` qualifies the source before any native
output exists. In release mode it requires all of these:

1. `pyproject.toml`, `src/articulate/__init__.py` and the three plugin
   manifests declare one version.
2. The version reads `MAJOR.MINOR.PATCH` in digits.
3. The detector closure matches `scripts/release_ruleset_baseline.json`, as
   `scripts/check_release_ruleset.py` checks it.
4. The working tree is clean.
5. `HEAD` equals the commit of the tag `v<version>`, and the workflow ref is
   that tag.

`publish.yml` also checks that the tag matches `pyproject.toml`, that every
console script resolves in a clean install, and that the stdio MCP server
answers.

## Steps

1. Branch from `main` and set the version in `pyproject.toml`,
   `src/articulate/__init__.py`, `claude-plugin/src/articulate/__init__.py` and
   the three plugin manifests.
2. Move the CHANGELOG entries from Unreleased to the new version. Open the
   section with one or two sentences on what the release does for the user.
   A date line or a list at the top stops the publish at its first gate.
3. Open a pull request from a branch named `release/<version>`, wait for CI
   to pass, then merge. On a release branch the Discover check runs with its
   gate on, the same gate `publish.yml` runs first.
4. Tag the merge commit on `main` with `v<version>` and push the tag. The tag
   alone starts nothing.
5. Publish a GitHub release for the tag, with the CHANGELOG section as notes:
   `gh release create v<version> --verify-tag --notes-file notes.md`.
6. Watch the publish workflow. When it finishes, install the version from PyPI
   into a clean virtual environment and run `articulate --version`.
