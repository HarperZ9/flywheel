"""parity_peer_notes_coverage.py -- the reasoning behind the nine owed rows.

`parity_coverage` read the three peers that publish a page index on
2026-09-06 and named capability areas the matrix did not score.
`parity_rows_coverage` turned nine of them into rows. These are the notes
for those rows, in the same shape as the rest of the audit trail: which half
of a row a peer has, which half it does not, and the page that says so.

Two things about the evidence are worth a reader's attention. The Codex and
Claude Code indexes carry a title and a description per page, so a cell there
rests on documentation text. The Cursor index is a list of bare URLs, so a
Cursor cell rests on a page path and is thinner evidence; where the path name
does not itself say what the page claims, the cell is PART rather than YES.

hermes and omp publish no index. Their cells are UNREAD on all nine, which
is not a finding about them. Four of these rows audit ABSENT here, and on
those rows a peer cell lowered without reading the page would shrink the gap
list in this project's favour, so a topic missing from an index reads UNREAD
rather than NO.
"""
from __future__ import annotations

NOTES: dict[str, str] = {
    "scheduled-runs":
        "All three ship it and this repository does not, which is why the "
        "row is here reading ABSENT. codex automations.md is titled "
        "Scheduled tasks and describes running tasks on a schedule or from "
        "app events. claude-code carries three pages: routines.md for "
        "routines that run on a schedule or react to GitHub events, "
        "scheduled-tasks.md for cron tools inside a session, and "
        "desktop-scheduled-tasks.md for recurring desktop runs. cursor has "
        "cloud-agent/automations.md and help/ai-features/automations.md, "
        "paths whose names carry the claim without a description behind "
        "them. Nothing here starts a run without a person, and the witness "
        "names the module that would.",
    "lifecycle-hooks":
        "All three declare hooks and so does this repository, so the row is "
        "witnessed and earns no star. codex hooks.md runs scripts or MCP "
        "tools during the Codex lifecycle. cursor has docs/hooks.md. "
        "claude-code names hooks in claude-directory.md among what .claude "
        "holds and in context-window.md as something that fires during a "
        "session. What differs is not the hook but the record: a firing "
        "here lands on the run's own receipt through accountable_hooks, and "
        "none of the three pages describes a hook firing as an auditable "
        "event rather than a side effect.",
    "subagent-teams":
        "All three ship delegation to child agents. codex "
        "agent-configuration/subagents.md configures custom Codex agents. "
        "cursor has docs/subagents.md. claude-code agents.md compares "
        "subagents, agent view, agent teams and dynamic workflows, and "
        "sub-agents.md creates them. Witnessed here through subagents and "
        "the rejoin path, so no star: this is a capability the field has, "
        "and a row that reported otherwise would be scoring the row set "
        "rather than the field.",
    "packaged-skills":
        "All three ship a skill package format. codex build-skills.md gives "
        "ChatGPT and Codex new capabilities, with enterprise/skills.md "
        "comparing workspace, filesystem and plugin skill controls. cursor "
        "has docs/skills.md and an analytics endpoint for skills adoption. "
        "claude-code names skills in features-overview.md alongside "
        "CLAUDE.md, subagents, hooks, MCP and plugins. The half that "
        "differs here is admission: skill_gate decides whether a skill runs "
        "rather than loading it because it is present, and only the codex "
        "enterprise page describes controls of that kind.",
    "self-hosted-runner-pool":
        "cursor is the clearest: cloud-agent/self-hosted.md with pool.md, "
        "my-machines.md and choose-runtime.md under it. claude-code "
        "self-hosted-environments-testing.md verifies a self-hosted runner "
        "image from CI. codex is UNREAD rather than NO. Its index carries "
        "cloud.md and environments/cloud-environment.md and nothing naming "
        "a pool of the operator's own machines, and this row audits ABSENT "
        "here, so a NO read off an index would shrink the gap list in this "
        "project's favour on evidence that cannot support it.",
    "usage-and-cost-accounting":
        "codex enterprise/chatgpt-work-usage-and-cost.md covers credit "
        "consumption, billing impact and spending controls. cursor exposes "
        "usage events, daily usage and pooled usage through its "
        "organization and team admin APIs. claude-code is PART: gateways.md "
        "reaches usage tracking and cost controls by routing through a "
        "self-hosted gateway, which puts the accounting in a product beside "
        "the tool rather than on the run. Witnessed here, and the half that "
        "differs is /api/usage/verify, where the figures are on a receipt "
        "that re-checks rather than a dashboard that has to be believed.",
    "browser-and-computer-control":
        "All three drive something outside the editor and this repository "
        "does not. codex has browser.md, computer-use.md and "
        "chrome-extension.md. cursor has agent/tools/browser.md and "
        "cloud-agent/self-hosted/computer-use.md. claude-code "
        "computer-use.md opens apps, clicks, types and reads the screen on "
        "macOS. The operator's other repositories have computer control; "
        "the Flywheel column is audited by reading this repository, so a "
        "capability in a sibling repository is not a capability here and "
        "the row reports ABSENT.",
    "own-code-vulnerability-scan":
        "All three scan the user's own code, which corrects the coverage "
        "entry that named two. codex security.md finds and remediates "
        "vulnerabilities through a plugin, CLI, SDK or cloud, with "
        "security/plugin/vulnerability-reports.md under it. cursor has "
        "security-agents.md and bugbot.md. claude-code claude-security.md "
        "scans a codebase and turns findings into patches, with "
        "security-guidance.md reviewing changes as they are written. "
        "ABSENT here. The credential-exposure-scan row is narrower and "
        "covers secrets in configuration, not defects in the code.",
    "generated-visual-artifacts":
        "codex image-generation.md generates and edits images, with "
        "visualizations and appshots pages alongside it. claude-code "
        "artifacts.md turns session output into live interactive pages, "
        "which is a visual artifact that is a page rather than an image. "
        "cursor is PART: agent/tools/canvas.md and agent/design-mode.md are "
        "paths with no description, and neither name says the agent "
        "produces a file. Witnessed here through design_studio and the "
        "typeface routes, so no star.",
}
