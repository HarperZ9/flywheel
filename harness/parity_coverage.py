"""parity_coverage.py -- what the peers ship that no row of this matrix scores.

`gaps 0` on the published page means no row where a peer declares a capability
and this repo audits ABSENT. That sentence is only about rows that exist. The
row set was written here, so a capability nobody thought to add a row for
cannot produce a gap, and the strongest number on the page would keep reading
zero while the hole grew. A matrix whose denominator is chosen by its author
needs the choice published beside the result.

This module is that publication. Each entry names a capability area found in a
peer's own page index, the peers that ship it, and what this project decided
about it. Two dispositions, and the difference matters:

    row-owed      a peer ships it, the matrix has no row, and one is owed
    out-of-frame  deliberately not scored, with the reason written down

`out-of-frame` is the load-bearing half. It is where a coverage control can be
turned back into decoration by declaring everything inconvenient to be someone
else's problem, so every entry carries a reason a reader can argue with rather
than a label.

Read on 2026-09-06 from the three published page indexes, each fetched whole:
cursor.com/llms.txt, learn.chatgpt.com/docs/llms.txt (the bare /llms.txt
answers 307 to it), and code.claude.com/docs/llms.txt. hermes and omp publish
no index, so their columns here say only what the source readings of the same
date found, and an empty hermes or omp mention is not an absence claim.
"""
from __future__ import annotations

#: The two answers an entry may carry. A third value would let a topic sit in
#: the set without saying which of the two it is, which is the state this
#: module exists to end.
DISPOSITIONS = ("row-owed", "out-of-frame")

#: Capability areas a peer ships that no row in `parity_rows.ROWS` scores.
#: `peers` names who was found shipping it, `where` names the pages it was
#: found on, and `reason` says why the disposition is what it is.
UNSCORED: tuple[dict, ...] = (
    {"topic": "scheduled and recurring runs",
     "peers": ("codex", "cursor", "claude-code"),
     "disposition": "row-owed",
     "where": "codex automations; cursor cloud-agent/automations; claude "
              "code scheduled-tasks and desktop-scheduled-tasks",
     "reason": "All three hosted peers let a run start on a clock or an "
               "event with nobody watching. That is the setting where a "
               "receipt is worth the most, because there is no operator in "
               "the room to notice a bad answer, and this matrix currently "
               "says nothing about it either way."},

    {"topic": "lifecycle hooks around a run",
     "peers": ("codex", "cursor", "claude-code"),
     "disposition": "row-owed",
     "where": "codex hooks; cursor hooks; claude code hooks and hooks-guide",
     "reason": "A hook is an operator-authored program that runs at a fixed "
               "point in the agent loop, and all three publish one. It is "
               "the nearest thing any peer has to a control point this "
               "project would want to record, so leaving it unscored hides "
               "the closest comparison the field offers."},

    {"topic": "subagents and multi-agent teams",
     "peers": ("codex", "cursor", "claude-code"),
     "disposition": "row-owed",
     "where": "codex agent-configuration/subagents; cursor subagents; claude "
              "code sub-agents, agent-teams, cross-session-messaging",
     "reason": "Delegation to another agent is scored here only through "
               "acp-delegation-receipt, which is about the protocol boundary. "
               "In-product delegation between agents of the same vendor is a "
               "separate surface and three peers document one."},

    {"topic": "packaged skills",
     "peers": ("codex", "cursor", "claude-code"),
     "disposition": "row-owed",
     "where": "codex build-skills, skills-and-plugins, enterprise/skills; "
              "cursor skills; claude code skills",
     "reason": "plugin-registry and plugin-marketplace score a catalog of "
               "tools and servers. A skill is a different unit, a bundle of "
               "instructions the model loads on demand, and scoring it under "
               "the plugin rows would report a capability this project has "
               "not been measured on."},

    {"topic": "self-hosted runner pools",
     "peers": ("cursor", "claude-code"),
     "disposition": "row-owed",
     "where": "cursor cloud-agent/self-hosted, /self-hosted/pool, "
              "/self-hosted/my-machines; claude code self-hosted-runner and "
              "the self-hosted-environments pages",
     "reason": "A pool of machines an operator owns, running agent work under "
               "their own control, is a shape this repo could witness. It is "
               "unscored, so the matrix is silent on the one part of the "
               "hosted plane that a local harness can actually answer."},

    {"topic": "cost and usage accounting",
     "peers": ("codex", "cursor", "claude-code"),
     "disposition": "row-owed",
     "where": "codex enterprise/chatgpt-work-usage-and-cost, "
              "enterprise/analytics-api, enterprise/usage-limits; cursor "
              "account/teams/analytics-api and ai-code-tracking-api; claude "
              "code costs, analytics, monitoring-usage, agent-sdk/"
              "cost-tracking",
     "reason": "What a run cost is a number a receipt could carry and none of "
               "these rows asks for it. All three peers publish accounting, "
               "and two of them expose it through an API."},

    {"topic": "browser and computer control",
     "peers": ("codex", "cursor", "claude-code"),
     "disposition": "row-owed",
     "where": "codex browser, computer-use, chrome-extension; cursor "
              "agent/tools/browser and cloud-agent/self-hosted/computer-use; "
              "claude code chrome and computer-use",
     "reason": "An agent driving a browser or a desktop takes actions outside "
               "the repository, where the boundary rows in this matrix stop "
               "applying. Three peers ship it and there is no row for what a "
               "record of such an action would have to contain."},

    {"topic": "scanning the user's own code for vulnerabilities",
     "peers": ("codex", "cursor"),
     "disposition": "row-owed",
     "where": "codex security/cli, security/plugin and the deep-scans, "
              "bulk-scans, vulnerability-reports, triage-backlog pages; "
              "cursor security-agents and bugbot",
     "reason": "credential-exposure-scan covers one narrow finding class. "
               "Codex publishes a scanning product with a triage backlog and "
               "exported findings, and Cursor ships review agents. A finding "
               "that cannot be re-derived later is exactly the artifact this "
               "project claims to improve, so the omission cuts against us."},

    {"topic": "generated images and visual artifacts",
     "peers": ("codex", "cursor"),
     "disposition": "row-owed",
     "where": "codex image-generation, image-inputs, visualizations, "
              "appshots, artifacts-viewer; cursor agent/tools/canvas and "
              "agent/design-mode",
     "reason": "A run that emits an image emits an artifact, and an artifact "
               "is hashable. No row asks whether a non-text output is bound "
               "to the run that produced it, which is a question this "
               "project is otherwise built to ask."},

    {"topic": "vendor-hosted execution",
     "peers": ("codex", "cursor", "claude-code"),
     "disposition": "out-of-frame",
     "where": "codex cloud and environments/cloud-environment; cursor "
              "cloud-agent; claude code cloud-environments and "
              "claude-code-on-the-web",
     "reason": "The flywheel column is audited by reading this repository. A "
               "vendor's own execution plane has nothing here to read, so the "
               "row would be permanently ABSENT and would report a product "
               "shape rather than a capability. The half of this that a local "
               "harness can answer is listed above as self-hosted runner "
               "pools, and that one is owed."},

    {"topic": "tenant administration",
     "peers": ("codex", "cursor", "claude-code"),
     "disposition": "out-of-frame",
     "where": "codex enterprise/* including governance, service-accounts, "
              "groups-and-provisioning and managed-configuration; cursor "
              "enterprise/*, account/teams/sso and scim; claude code the "
              "managed-settings and gateway administration pages",
     "reason": "Seat provisioning, single sign-on and spend policy are bought "
               "by an organization and audited by procurement. This project "
               "has no tenant to administer, and a row scoring it would "
               "measure company size. The one part of that tree that touches "
               "this matrix, an org-level audit log, is already written up "
               "under receipt-on-every-answer as the near miss it is."},

    {"topic": "per-editor extensions",
     "peers": ("codex", "cursor", "claude-code"),
     "disposition": "out-of-frame",
     "where": "codex codex/ide, integrated-terminal, chrome-extension; "
              "cursor integrations/jetbrains and xcode; claude code vs-code "
              "and jetbrains",
     "reason": "This matrix scores the protocols an editor speaks, which is "
               "what lsp-go-to-definition, dap-debug-session, "
               "acp-delegation-receipt and mcp-client-and-server are for. An "
               "extension distributes an existing capability to one more "
               "editor, so counting extensions would score the same "
               "capability once per editor and reward a distribution budget."},

    {"topic": "voice input and accessibility",
     "peers": ("codex", "claude-code"),
     "disposition": "out-of-frame",
     "where": "codex features/voice; claude code voice-dictation and "
              "accessibility",
     "reason": "How a person gets words into the prompt does not change what "
               "the run does or what a record of it can say. This is a real "
               "product difference and it is not one this matrix is built to "
               "measure. Accessibility work is worth doing on its own terms "
               "rather than as a cell in a competitive table."},
)

ROW_OWED = tuple(e["topic"] for e in UNSCORED
                 if e["disposition"] == "row-owed")


def coverage_summary() -> dict:
    """The counts that go on the page beside the gap count."""
    return {"unscored_topics": len(UNSCORED),
            "row_owed": len(ROW_OWED),
            "out_of_frame": len(UNSCORED) - len(ROW_OWED),
            "read_on": "2026-09-06"}
