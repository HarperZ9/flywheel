# Native ServiceDesk incident review

This path lets the desktop Receipts view recheck a ServiceDesk incident evidence
directory through the local gateway. It is a reader for
`service-desk-incident-env-review/v1`; it does not run a model, replay submitted
actions, execute HTML, write report files, or replace the product verifier.

## Gateway route

- `POST /api/enterprise-envs/service-desk-incident/review`
- Private custody through `/api/enterprise-envs/`
- Request body: `{"artifact_dir_ref": "relative/path-under-run-root"}`
- Response schema: `flywheel.enterprise-env-review/v1`

The directory reference is resolved under the gateway run root. Absolute paths,
drive-qualified paths, `file://` references, parent traversal, links, junctions,
and artifact trees that resolve outside the admitted directory are refused before
the product review runs.

The product review recursively reads the selected directory, so path admission
alone is not a safe handoff boundary. Before invoking the trusted local product,
the gateway copies the selected artifact through the existing private artifact
filesystem custody layer into a temporary snapshot directory. The product reviews
that snapshot, not the caller-controlled original path. This bounds the review to
regular files that were read through no-follow descriptor or handle operations;
it does not claim the whole host or original directory remained unchanged after
the snapshot was made.

The route loads the optional product through
`harness.enterprise_envs.compat.load_service_desk_product()` and calls
`product.review_artifacts(snapshot_dir)`. The returned report must include the
complete `service-desk-incident-env-review/v1` shape: verification, claimed
outcome, recomputed outcome, source-integrity, synthetic-task, record-consistency,
external-trust layers, and limits. Missing or older product support returns
`PRODUCT_UNAVAILABLE` or `PRODUCT_UPGRADE_REQUIRED` and points to the
`flywheel-env-service-desk-incident` 0.2.0 release:

https://github.com/HarperZ9/flywheel/releases/tag/env-service-desk-incident-v0.2.0

## Finding semantics

A failed ServiceDesk review is still a successful route response when the product
returns a complete report. For example, a self-consistent but false-success bundle
can keep recorded case flags as pass while recomputed task evidence returns
`target_incident_not_open`. The desktop panel renders claimed and recomputed
outcomes separately so this does not look like a transport error or a pass.

The route removes local artifact paths from the JSON response before it reaches
the desktop client. It also rejects report strings that still contain host paths
or secret-shaped content after that sanitization.

## Desktop surface

The Receipts view now includes a ServiceDesk evidence review panel beside the
existing witness and packet recheck tools. The panel asks for the run-root
relative artifact directory ref, shows claimed versus recomputed outcome, lists
failure codes and evidence-layer states, and keeps the synthetic-boundary and
absent-external-trust limits visible.

The UI does not render raw action logs or raw report JSON. It treats missing,
older, or partial product support as an unavailable upgrade state.
