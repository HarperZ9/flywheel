# Releasing Flywheel

One annotated tag, `vMAJOR.MINOR.PATCH`, ships a release. This page says what
the tag starts, what a person still does, and how to rehearse it.

## What the tag starts

Pushing the tag starts two workflows.

`publish.yml` runs these jobs in order:

1. **plan.** The tag, `pyproject.toml`, `desktop/pubspec.yaml` and
   `desktop/lib/version.dart` must name one version. `RELEASE-NOTES-<version>.md`
   must exist, open with `# Flywheel <version>`, link `docs/LICENSING.md`, and
   print the shipped rule-pack digest. `CHANGELOG.md` must have a dated section
   for the version. A placeholder left in the notes, the changelog or
   `SECURITY.md` stops the run.
2. **build.** The wheel and the sdist, then the files a runner can build with
   no secret: the plugin and skill zips, the source tools plugin and the VS
   Code extension. Each of those is built twice and the two results must be
   the same bytes. Every file is listed in a sums file.
3. **gates**, on Linux and Windows. The built wheel is installed in a clean
   environment and the checkout's own `harness` folder is moved away, so the
   gates run on what the wheel carries:
   - the scope migration check;
   - every asset against its sums file;
   - `python scripts/verify_compat_records.py --control`: the record set from
     each 1.x minor verifies, and no record with one changed byte does;
   - every test marked `release_gate`, which includes the timing budgets
     for the coding session (50 ms) and the gateway (25 ms of its own time)
     and the one-second budget for the record check;
   - `flywheel gate`, which must end with `verdict=PASS rewitness=MATCH`;
   - one coding request against a scripted model.
4. **publish.** The wheel and the sdist go to PyPI by Trusted Publishing. No
   token is stored.
5. **release.** The GitHub release is created with the notes file and the
   assets from step 2. An existing release is never written over. The job
   then starts the release media and docs site workflows.
6. **verify-pypi**, on Linux, macOS and Windows. PyPI must serve files with
   the digests step 2 wrote. A fresh install from PyPI must print the version
   and pass `flywheel gate`.

Nothing is published unless every gate in step 3 passed on both systems.

`desktop-release.yml` builds the Windows installer, the native MCPB companion
and their sums files from the same tag, runs the installed-app acceptance, and
stores the result as the workflow artifact `windows-installer-candidate`. It
has read-only permission and creates no release.

## Release assets

| Asset | Built by |
|---|---|
| `flywheel_verify-<version>-py3-none-any.whl`, `flywheel_verify-<version>.tar.gz`, `python-SHA256SUMS.txt` | `publish.yml` |
| `flywheel-evidence-task-<n>-plugin.zip`, `flywheel-evidence-task-<n>-skill.zip`, `plugin-SHA256SUMS.txt` | `publish.yml` |
| `flywheel-tools-<version>-source-plugin.zip`, `source-plugin-SHA256SUMS.txt` | `publish.yml` |
| `flywheel-code-<n>.vsix`, `vscode-SHA256SUMS.txt` | `publish.yml` |
| Release videos, posters and media zips | `release-media.yml`, started by `publish.yml` |
| `Flywheel-Setup-<version>-x64.exe`, `SHA256SUMS.txt` | `desktop-release.yml`; added by hand, below |
| `flywheel-tools-<version>-win-x64.mcpb`, `native-MCPB-SHA256SUMS.txt` | `desktop-release.yml`; added by hand, below |

## What a person does

Before the tag:

1. Open a release pull request that sets the version at every site (the three
   above, `CITATION.cff`, the README badge, the `QUICKSTART.md` line and the
   `docs/GITHUB-ACTION.md` pin), adds `RELEASE-NOTES-<version>.md`, and turns
   the changelog's Unreleased section into a section for the version. On the
   day of the release, `python scripts/release_assets.py stamp --date
   YYYY-MM-DD` writes the date wherever a `RELEASE-DATE` placeholder waits
   for it. Then `python scripts/release_assets.py check --tag v<version>
   --release` must print `release check clean`.
2. Run the dry run (next section) on that branch.
3. Merge the pull request and wait for the checks on main.
4. `git tag -a v<version> -m "Flywheel <version>"` on the merge commit, then
   `git push origin v<version>`.

After the tag:

5. When `desktop-release.yml` finishes, download its
   `windows-installer-candidate` artifact. Check each file against the sums
   file beside it, then add the installer, the MCPB and their two sums files
   to the release with `gh release upload`. The plugin and source plugin
   zips in the candidate must have the digests already on the release.
6. Run `python scripts/package_manager_bump.py` and merge the Homebrew and
   Scoop files in a follow-up pull request. `package-managers.yml` installs
   through both on that pull request.

## Dry run

Start `publish.yml` by hand on any branch:

```bash
gh workflow run publish.yml --ref <branch>
```

A dry run does steps 1 to 3 in full and publishes nothing. It uploads the
would-be release as the workflow artifact `release-dry-run`: the assets, a
list of their digests, and the notes file. On a branch the source tools plugin
is built in its development form, because the release form refuses a commit
that is not the version tag.

A run publishes only from a `v*` tag ref. If a tag's run stopped after the
gates, start it again on the tag with `gh workflow run publish.yml --ref
v<version> -f dry_run=false`.

## If something goes wrong

- A gate fails: nothing was published. Fix on main, delete the tag, and tag
  the fixed commit.
- PyPI has the version and a later job failed: a PyPI version cannot be
  uploaded twice or withdrawn. Finish the release by hand from the run's
  `release-assets` artifact, or yank the version on PyPI and release the next
  patch version.
