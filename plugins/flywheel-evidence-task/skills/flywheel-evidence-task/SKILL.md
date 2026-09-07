---
name: flywheel-evidence-task
description: Produce source-linked Flywheel or Bulletin evidence packets with measured claims, falsification controls, and reported/checked/unknown boundaries. Use for user-authorized research, readiness, feedback, release, or observatory checks.
license: FSL-1.1-MIT
metadata:
  version: "0.1.0"
  author: "Zain Dana Harper"
---

# Flywheel Evidence Task

Use this skill when the user asks for an inspectable Flywheel or Bulletin research, readiness, release, feedback, or observatory check. The output is a compact evidence packet that a human or downstream agent can audit.

Compatibility: this skill follows the Agent Skills directory format and is intended for ChatGPT, Codex, Claude Code, and similar agents. MCP tools are optional and must be discovered at runtime.

Read [references/constraints.md](references/constraints.md) when the task includes publication, public projection, external posting, tool-readiness claims, or private-source risk.

## Workflow

1. State the decision or claim the check supports. Label starting premises as `proposed`, `reported`, `checked`, or `unknown`.
2. Inventory the allowed sources. Prefer public or user-supplied sources for public outputs. Copy, hash, or otherwise pin mutable inputs when the task needs replay.
3. Discover available tools in the active host before using them. Map capabilities at runtime:
   - source capture and provenance;
   - workspace or repository mapping;
   - measured claim assessment, registry, replay, or report generation;
   - cross-lane routing or witnessed planning.
   Do not assume host-specific tool identifiers, REST endpoints, or hidden runners.
4. Define the measurement before the conclusion. Include a falsification method, an ordinary-success control, and a false-success control.
5. Keep MCP primitives separate. Tools perform operations, resources provide context/data, prompts provide reusable templates, and MCP-imported skills are static snapshots unless the host says otherwise.
6. Mark missing measurement as `UNVERIFIABLE`. A green status, available tool list, receipt seal, or model agreement is not readiness, truth, or independent review.
7. Return a compact packet with source links, artifact paths, hashes or receipts, verdicts, exclusions, limitations, and the strongest next action.

## Output shape

Use this shape unless the user requested another format:

```text
Decision or claim:
Sources allowed:
Checked:
Reported:
Unknown or unverifiable:
Measurements:
Controls:
Artifacts:
Does establish:
Does not establish:
Next action:
```

## Boundaries

- This skill does not grant standing execution authority, monitoring, public posting, production deployment, or marketplace submission by itself.
- Do not include raw transcripts, credentials, private runtime paths, unpublished scratch data, or hidden inventories in public artifacts.
- Do not manufacture activity. Empty catalogs, self-agreement, dry routes, and liveness-only checks must stay labeled as limitations.
- If the user has authorized public-source packaging, prepare the package and validation materials. Keep separate approval only for irreversible external side effects the user has not already authorized.
