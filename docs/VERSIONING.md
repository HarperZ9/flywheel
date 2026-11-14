# Versions and compatibility

Flywheel uses semantic versions, MAJOR.MINOR.PATCH. The package on PyPI
(`flywheel-verify`), the Windows installer, the VS Code extension's bundled
command and the docs site all ship from one annotated git tag, `vMAJOR.MINOR.PATCH`.
`flywheel --version` prints the version you have and `flywheel update` tells
you whether a newer one exists.

## What each part of the number means

- A patch release (1.8.0 to 1.8.1) fixes bugs. It adds no command, flag or
  output field.
- A minor release (1.8 to 1.9) adds commands, flags, tools, output fields,
  hook events or providers. Everything that worked before keeps working.
- A major release (1.x to 2.0) is the only place a breaking change can land.

## What counts as a breaking change

A change breaks compatibility when a script, config file or record that worked
with the previous release stops working or changes meaning. That covers:

- Command names, flag names and their meaning, and exit codes.
- JSON output schemas, named by a `schema` field such as
  `flywheel.code-result/v1`. A new field is not breaking; removing or renaming
  a field, or changing its type, is.
- Session, receipt and ledger formats, also named by schema. A session saved
  by one 1.x release resumes in every later 1.x release.
- Config file shapes: `permissions.json`, `mcp.json`, `hooks.json`, and the
  Markdown front matter of commands, subagents and skills.
- Tool names the model sees, and MCP tool names Flywheel serves.
- The environment variables listed on the [configuration](CONFIGURATION.md)
  page.

Text meant for people, such as help text, log lines and the wording of a
prompt, can change in any release. Parse the JSON outputs, not the text.

## Records stay checkable

A receipt or ledger is only useful if it can still be checked later. Each
format carries its schema name and version. When a format changes, it gets a
new schema version, and the checker for every older version stays in the
package. A major release does not end this: a record written by any 1.x
release reads and verifies with every 2.x release, with its original bytes.

2.0 renamed the field that says what a record covers from `does_not_prove`
to `scope`. A 1.x record keeps the older name and its own schema version, and
2.x reads it with the older vocabulary. A record that carries the list under
both names is refused, because no release writes one.

The repository holds the evidence for this promise. Under
`tests/fixtures/compat/records-1.x` there is one sealed record set from each
1.x minor, 1.0 to 1.9, written by that release as published on PyPI. The
test suite verifies every one on each change, and
`python scripts/verify_compat_records.py` runs the same check from a
checkout. The check has controls: one byte changed at any position in any
of the files must read DRIFT or FAIL, and a reader that answers MATCH to
everything fails the control test.

## Deprecation

Before a command, flag or field is removed in a major release, the minor
release before it marks it deprecated: the CHANGELOG names it, and using it
prints one warning line that names the replacement. Removal never happens in
a minor or patch release.

### The 2.0.0 exception (2026-11-14)

2.0.0 shipped breaking changes without the notice this section requires. No
1.x release marked the `does_not_prove` field, the word counts in the served
`usage` field or the changed session defaults as deprecated, and none printed
a warning for them. The author decided on 2026-11-14 to release 2.0.0
directly, with no notice-only 1.9.1 before it. The two old hook scripts are
the one removal that did have a notice: they printed a deprecation line
through 1.x.

This is a one-time exception. The rule above applies again from 2.0.0 on.

What to do if you are on 1.x:

- Read [Moving from 1.x to 2.0](MIGRATING-2.0.md) before you upgrade. It lists
  every renamed field, changed default and removed script, with the setting
  that restores the 1.x behaviour where one exists.
- If a script parses Flywheel's JSON, pin `flywheel-verify<2` until the script
  reads the new names. 1.9.x keeps working and gets security fixes for the
  period under "Which releases get fixes".
- Keep your old records. Nothing needs converting: 2.x verifies them as they
  are.

## Python versions

Flywheel needs Python 3.11 or newer. Dropping a Python version is announced in
the CHANGELOG one minor release ahead and happens no sooner than that
version's end of life upstream.

## Which releases get fixes

Fixes ship in the next release. Older releases do not get backported fixes,
with one exception: 1.9.x receives security fixes for 90 days after 2.0.0 is
released, and no other fixes. Upgrade with `flywheel update --apply` or your
package manager. Each
release's license terms, including its date of conversion to MIT, are on the
[licensing](LICENSING.md) page.
