# Plan view — spec-driven planning over profiles and a chosen project

Date: 2026-07-13. Status: approved by the standing goal directive (resume item 1);
built autonomously on the /goal loop.

## Purpose

Turn a plain goal into a checkable plan BEFORE anything runs, then hand the plan
to the workflow engine as a staged, receipted run. The forge (`POST /api/forge`)
produces the criterion-bearing spec: validation gates each marked externally
checkable or not, and a confidence score grounded in that ratio, never in vibes.
The deep profile supplies the operating discipline (planning steps, workflow,
requested gates); the registered project supplies the root. Nothing in this view
authors its own verdicts: the gate flags and confidence come from the engine.

## Approaches considered

1. Forge-only composer (no execution). Too thin: misses the "workflow engine"
   half of the item.
2. Forge + profile + project pickers, PRP rendered with gate verdicts, and a
   one-click handoff to `POST /api/workflow` with the chosen project as root.
   CHOSEN: complete item, reuses WorkflowRun models and cards, and begins
   resume item 2 (project pickers on a working surface).
3. Also persist plans as store entities. Deferred: that is resume item 3's
   single-source-of-truth slice.

## Components

- `lib/models/plan_models.dart` — `ForgedPlan.fromJson` over `flywheel.prp/v1`:
  goal, taskType, confidence (1..10), externalGateRatio, wellPosed,
  gates `[{check, externallyCheckable}]`, rendered prompt. Defensive: missing
  fields degrade, never crash.
- `lib/views/plan_view.dart` — the destination. Composer (project picker from
  `client.projects()`, profile picker from `client.profiles()`, endpoint picker
  from `client.endpointRoster()`, goal field, forge button). Result: stat tiles
  (confidence, external-gate ratio, gate count), per-gate rows with a verdict
  pill (`oracle` → verified, `manual` → unverifiable — checkability IS the
  verdict), the profile's planning steps, the full PRP prompt as selectable
  mono, and a "Run as workflow" handoff rendering `WorkflowRunCard`.
- Shell: new rail destination `Plan` (abbr `PN`) at index 1, after Projects.
  All later indexes shift by one; the shell test moves to sixteen destinations.

## Honest nulls

- No registered project: the picker states it and points at Projects; forging
  still works (a plan does not require a root), running as a workflow does not.
- `well_posed: false`: a drift-tinted note says the criterion was
  auto-proposed and must be confirmed.
- Profile gates are requested defaults, never grants: write/exec checkboxes
  start false, exactly as in Workflows.

## Failure modes

- Engine offline → FwEmpty naming `flywheel up`.
- Forge error body (`{"error": ...}`) → HonestNull with the message.
- Workflow run failure → HonestNull; a verify step without exec grant reports
  UNVERIFIABLE via the existing step verdict mapping.

## Tests

- Shell test: sixteen destinations, `Plan` present.
- `plan_models` unit tests: full PRP parses; empty JSON degrades to defaults;
  gate checkability maps to the right verdict string.
- Plan view offline test: states the fact and the command.

## Typography note (operator request, canon-held)

Richness comes from range inside the two families, not new ones: large
tabular-figure stat values (w700), tracked mono kickers, mono plan-step
numerals, selectable mono provenance. No third typeface.
