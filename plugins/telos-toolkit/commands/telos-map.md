---
description: Map the workspace with Index. Build or read the repo/context graph so you know which repo owns what.
---

# Map the workspace with Index

Optional focus (a repo, path, or area): **$ARGUMENTS**

Use the `index` MCP server provided by this plugin to build or read the
workspace map.

1. Query the `index_*` tools for the repo graph, context, or workspace map. If a
   focus was given above, scope the query to it; otherwise return the top-level
   repo map.
2. Report which repo owns the concern in question and the paths that matter for
   it, so the next step (edit, verify, gather) starts in the right place.
3. Cross-check against `project-docs/WORKSPACE-MAP.md` when it is present. If the
   map and the index disagree, surface the discrepancy rather than silently
   trusting one.

The CLI equivalent is the `index` console script (from the `index-graph`
package).
