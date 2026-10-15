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
package for the whole major release line. A record written by 1.6.0 verifies
with 1.9.0.

## Deprecation

Before a command, flag or field is removed in a major release, the minor
release before it marks it deprecated: the CHANGELOG names it, and using it
prints one warning line that names the replacement. Removal never happens in
a minor or patch release.

## Python versions

Flywheel needs Python 3.11 or newer. Dropping a Python version is announced in
the CHANGELOG one minor release ahead and happens no sooner than that
version's end of life upstream.

## Which releases get fixes

Fixes ship in the next release. Older releases do not get backported fixes
today; upgrade with `flywheel update --apply` or your package manager. Each
release's license terms, including its date of conversion to MIT, are on the
[licensing](LICENSING.md) page.
