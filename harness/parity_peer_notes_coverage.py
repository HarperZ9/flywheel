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
is not a finding about them. A peer cell lowered without reading the page
would shrink the gap list in this project's favour, so a topic missing from
an index reads UNREAD rather than NO whatever this project's own verdict on
the row happens to be.

Four rows audited ABSENT when the notes were written. All four have since
landed, and the note on each says what the work turned out to differ in
rather than dropping the gap and leaving the row looking like it was always
covered.
"""
from __future__ import annotations

NOTES: dict[str, str] = {
    "scheduled-runs":
        "All three ship it and this repository did not, which is why the "
        "row was written. codex automations.md is titled "
        "Scheduled tasks and describes running tasks on a schedule or from "
        "app events. claude-code carries three pages: routines.md for "
        "routines that run on a schedule or react to GitHub events, "
        "scheduled-tasks.md for cron tools inside a session, and "
        "desktop-scheduled-tasks.md for recurring desktop runs. cursor has "
        "cloud-agent/automations.md and help/ai-features/automations.md, "
        "paths whose names carry the claim without a description behind "
        "them. Witnessed here through scheduler and /api/schedule. What "
        "differs is that a firing is a record with the trigger on it, so a "
        "run nobody watched can still be shown to have been due.",
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
        "a pool of the operator's own machines, and a NO read off an index "
        "would rest on evidence that cannot carry it. Witnessed here "
        "through runner_pool and /api/runners. What differs is where "
        "membership is settled: a machine joins by spending a ticket the "
        "operator minted, may advertise only the labels that ticket "
        "granted, and every enrolment, dispatch and lease sits on a chain "
        "that refuses the next write once an earlier row is edited. None of "
        "the three pages describes the roster as anything a reader could "
        "check without asking the party that runs it. What it does not "
        "claim is attestation: a compromised host holding a real ticket is "
        "a real member, so the property is control over membership rather "
        "than knowledge of the hardware.",
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
        "All three drive something outside the editor. codex has "
        "browser.md, computer-use.md and "
        "chrome-extension.md. cursor has agent/tools/browser.md and "
        "cloud-agent/self-hosted/computer-use.md. claude-code "
        "computer-use.md opens apps, clicks, types and reads the screen on "
        "macOS. Witnessed here through browser_control and /api/browser. "
        "The half that differs is that the gate and the record are one "
        "write: the policy is the session's first row, every attempt lands "
        "on the chain carrying its verdict, and a refusal is kept, so a "
        "constrained run and a run that did nothing do not read alike "
        "afterwards. Three limits are worth stating beside the row. Typing "
        "into a credential-shaped field is refused before the policy is "
        "consulted, so no policy can permit it. A non-http scheme never "
        "resolves. Actuation sits behind a driver seam and none is bundled, "
        "so with nothing bound the engine decides, records, and reports "
        "performed as false rather than implying a screen moved.",
    "own-code-vulnerability-scan":
        "All three scan the user's own code, which corrects the coverage "
        "entry that named two. codex security.md finds and remediates "
        "vulnerabilities through a plugin, CLI, SDK or cloud, with "
        "security/plugin/vulnerability-reports.md under it. cursor has "
        "security-agents.md and bugbot.md. claude-code claude-security.md "
        "scans a codebase and turns findings into patches, with "
        "security-guidance.md reviewing changes as they are written. "
        "Witnessed here through vulnerability_scan and "
        "/api/scan/vulnerabilities. The credential-exposure-scan row is "
        "narrower and covers secrets in configuration, not defects in the "
        "code.",
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
