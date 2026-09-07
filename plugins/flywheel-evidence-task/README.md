# Flywheel Evidence Task

A skill for checking Flywheel and Bulletin claims, reviewing public feedback,
and producing source-linked evidence packets. It separates reported claims,
measurements, missing evidence, and proposed next actions.

Version: 0.1.0. License: [FSL-1.1-MIT](LICENSE).

## Install

For an Agent Skills host, copy `skills/flywheel-evidence-task` into the skill
directory documented by that host. Keep its references and examples together.
In Codex, the user skill directory is `~/.agents/skills`. Restart or refresh
skill discovery as your host requires.

For Claude Code, register this repository's marketplace:

```text
/plugin marketplace add HarperZ9/flywheel
/plugin install flywheel-evidence-task@flywheel-skills
```

For Codex plugin discovery from a checked-out repository:

```text
codex plugin marketplace add .
codex plugin add flywheel-evidence-task@flywheel-skills
```

Run those Codex commands from the repository root. The marketplace entry points
at this plugin directory. Installation behavior depends on the host version.
The manifests are validated; third-party directory approval and live host
installation are separate from this source package.

## Use

Ask your agent to use `flywheel-evidence-task` to assess a specific claim or
feedback thread. Give it the sources and the decision the result should inform.
See [the workflow](skills/flywheel-evidence-task/SKILL.md) and its examples.

MCP tools such as Gather and Crucible are optional. The skill discovers available
tools at runtime and does not install servers, copy credentials, grant execution,
or publish anything by itself. A host with source-reading tools can use it
without the full Flywheel engine.

## MCP resources and downloads

From a checkout containing this change, `python -m harness.local_mcp` exposes
the skill and its constraints through `resources/list` and `resources/read`.
The resource identifiers are:

```text
flywheel://skills/flywheel-evidence-task/SKILL.md
flywheel://skills/flywheel-evidence-task/references/constraints.md
```

Resource listings include skill version, SHA-256 and byte count. The files are
included in wheels built from this checkout. This does not add them retroactively
to an older engine package or installer. Resources are readable context; this
server does not advertise the draft `skills/list` import extension.

Build standalone skill and plugin ZIPs from the repository root:

```text
python scripts/build_skill_bundle.py --out build/skill-downloads
```

The output includes SHA256SUMS and manifest.json. Only named public package
files enter either archive. Repeated builds from unchanged content produce
identical archives. The standalone ZIP includes the license and skill folder;
the plugin ZIP also includes manifests and installation documentation.

## Compatibility and validation

The skill uses the [Agent Skills format](https://agentskills.io/specification).
The package includes Codex and Claude plugin manifests. A package that validates
does not establish marketplace listing, task correctness, or compatibility with
every product bearing those vendors' names.

The development exercise included correct, tampered, and missing-source replay
controls. It caught an empty capture caused by a source filter. These controls
test evidence handling; they do not establish that an arbitrary claim is true.

Format references: [Codex plugins](https://developers.openai.com/plugins/build/plugins),
[Claude marketplaces](https://code.claude.com/docs/en/plugin-marketplaces),
and [MCP resources](https://modelcontextprotocol.io/specification/2025-06-18/server/resources).
