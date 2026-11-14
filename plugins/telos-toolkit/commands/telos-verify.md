---
description: Verify a claim with Crucible. Register it, measure it, and read the MATCH / DRIFT / UNVERIFIABLE verdict.
---

# Verify a claim with Crucible

The claim to verify: **$ARGUMENTS**

Guide the operator through Crucible's register -> measure -> witness loop using
the `crucible` MCP server provided by this plugin.

1. Restate the claim as a checkable proposition. If it has no measurable
   observable, say so and stop. An unmeasurable claim returns UNVERIFIABLE, not
   a pass.
2. Register the claim and its measurement substrate (predicted value,
   tolerance, and how the observed value is obtained) using the `crucible_*`
   tools. If a substrate JSON is needed, describe the fields: `predicted`,
   `tolerance`, `observe`.
3. Run the measurement and report the verdict verbatim: MATCH, DRIFT, or
   UNVERIFIABLE. Do not soften a DRIFT or UNVERIFIABLE into a pass.
4. If the operator prefers the CLI, the equivalent is the `crucible` console
   script (from the `crucible-bench` package).

Note: the registry showing MATCH is only as strong as the deviation the claim
supplied. State that caveat when the observed value was author-supplied rather
than independently measured.
