# Constraints

## Claim labels

- `proposed`: a planned or requested claim with no source check yet.
- `reported`: a claim found in a source but not independently measured here.
- `checked`: a claim measured against a named method and source.
- `unknown`: a claim outside the available evidence.
- `UNVERIFIABLE`: a claim that needs measurement but lacks a valid measurement.

## Public-source boundary

Use public or user-approved artifacts for any public projection. Do not export raw conversations, private inventories, credentials, local-only scratch paths, debug dumps, unpublished runtime state, or data whose publication status is unclear.

## Tool and MCP boundary

Discover tool schemas in the current host before use. Different hosts can expose the same capability under different names. Treat MCP as three separate runtime primitives:

- tools: callable functions that can read, compute, or act;
- resources: context or data that a client may read;
- prompts: user-invoked templates or workflows.

A skill distributed through an MCP server is a packaging and import path. It is not the same as an MCP tool call, and a submitted snapshot may not update live at runtime.

## Measurement boundary

Check that a source capture actually contains the intended sources. A sealed
empty catalog is still empty. For Gather document capture, omit `scope` unless
an exact substring filter is intended; it is not a prose research objective.
Directory walkers may omit source-code extensions, so use an explicit file
when needed and confirm nonempty catalog and receipt coverage.

For video or forum feedback, preserve source URLs, capture time, selection
order, sample cap, reply inclusion, duplicates, and exclusions. Distinguish
sample count from total comments. Keep dissent and failed captures. Extract
ideas as hypotheses, not representative demand; public replies can still
contain personal details that do not belong in product documentation.

Define the falsifier before drawing the conclusion. A valid receipt can prove that bytes or metadata were preserved; it does not prove semantic truth. A model rechecking its own answer is not independent review.

Required controls:

- ordinary-success control: a known-good input or replay should pass;
- false-success control: a tampered, missing, stale, or contradictory input should fail or become `UNVERIFIABLE`.

## Readiness boundary

Liveness is not readiness. A status endpoint, installed package, tool list, or green doctor result only establishes the property it measured. Keep model availability, tool availability, MCP handshake success, workflow readiness, and external publication status separate.
