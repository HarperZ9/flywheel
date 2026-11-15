# Source

This repository holds the Flywheel Evidence Task plugin at its root, so the
Claude plugin directory can install it on its own. The plugin is maintained in
the Flywheel repository:

- Source folder: https://github.com/HarperZ9/flywheel/tree/main/plugins/flywheel-evidence-task
- Copied from Flywheel commit: 07561b53dd2a800608c564437f6817b20cb2754c

## What is copied unchanged

`skills/`, `.claude-plugin/icon.png`, `PRIVACY.md` (except the contact link),
`LICENSE`, `LICENSE-ATTRIBUTION.md` and `CHANGELOG.md`.

## What differs here

- `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`: `repository`
  and the documentation link point at this repository.
- `.claude-plugin/marketplace.json`: added, so `/plugin marketplace add
  HarperZ9/flywheel-evidence-task` works.
- `README.md`: the listing page for this repository. The build and release
  notes stay in the Flywheel copy.
- `PRIVACY.md`: the contact link points at this repository's issues.
- `SOURCE.md`, `.gitignore`: this file and the ignore rules.

## Update this copy

1. Change the plugin in the Flywheel repository and merge it there.
2. Copy `plugins/flywheel-evidence-task` from that Flywheel commit over this
   repository, keeping the files listed under "What differs here".
3. Update the commit above, raise `version` in both manifests when the skill
   changes, and open a pull request here.

The plugin has no server code. When it gains any, keep that code inside this
repository so an install of this folder alone runs.
