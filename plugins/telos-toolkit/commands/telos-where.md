---
description: Find where something lives. Point at project-docs/WORKSPACE-MAP.md and route to the right flagship tool.
---

# Where does it live?

What you are looking for: **$ARGUMENTS**

Answer the "where does this live / where should this go" question.

1. Read `project-docs/WORKSPACE-MAP.md` in the folder that holds your
   repositories, when it exists. It is the index of repos, docs, research, plans,
   and specs. If it answers the question, return the concrete repo and path.
2. If the map does not resolve it, route by intent using the flagship MCP tools
   (see the `workspace-navigation` skill for the full routing table):
   - which repo / context -> `index`
   - a source or paper -> `gather`
   - a verdict on a claim -> `crucible`
   - task routing / ledger -> `forum`
   - a lesson or study plan -> `learn`
3. Return a location, not a guess. If nothing resolves, say the location is
   unknown and name the next check (a WORKSPACE-MAP entry to add, or the tool to
   run).
