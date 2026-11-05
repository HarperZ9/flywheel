# Publish metadata: the check and the gate

A published file can name its author in places nobody reads on screen: EXIF and
PNG text chunks, a PDF `/Author`, a docx creator, a local path in a test fixture,
the build machine's name, or a personal address in a fetch script's User-Agent.
Two scripts handle this before anything ships.

## The check

`scripts/check_publish_metadata.py PATH --mode report|fail|fix` reads every
tracked file and names each finding by category and label, never by value, so a
CI log does not republish it. `fix` strips image, PDF and Office metadata in
place and leaves text alone. Private patterns come from places that never ship:
the machine's own name, the git global `user.email`, and an untracked deny list
of regexes, one per line, from `--deny-list`, the `PUBLISH_DENYLIST` variable, or
the gitignored `scripts/.publish-denylist.txt`.

## The gate

`scripts/publish_metadata_gate.py [ROOT]` blocks a publish that adds metadata.
The public tree carried 1,370 findings in 214 files when the gate was frozen on
2026-11-04, nearly all workspace paths in test fixtures and scripts. Those counts
live in `project-docs/records/2026-11-04-publish-metadata-baseline.json` as path,
category and count, with no matched value. The gate fails when:

- a file's count for a category grows past its frozen count;
- a file outside the baseline has any finding;
- any private pattern matches (machine name, git global email, deny list). The
  baseline is written from the generic patterns only, so these always block.

The baseline only shrinks. `--write-baseline` refuses a larger count unless
`--allow-growth` is passed, and a cleaned file drops out of it.

Where it runs:

- `scripts/publish_public.py` runs it over the staging tree after
  `publish_lint --strict` and before any push. `--deny-list FILE` passes a deny
  list through. The export never copies `scripts/.publish-denylist.txt`.
- CI runs it over the checkout in the `publish_metadata` job, with the generic
  patterns only, since the runner holds no deny list.

## Limits

The text patterns are regexes over lines. A path split across two lines, or an
identifier spelled in a form no pattern names, passes. Git author and timezone
findings stay warnings: they describe history, which a noreply address and
`TZ=UTC` fix going forward.
