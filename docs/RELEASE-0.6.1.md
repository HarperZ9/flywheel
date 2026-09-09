# Flywheel 0.6.1

Flywheel 0.6.1 focuses on three operator outcomes. Cached answers re-enter the current acceptance path before they can be reused. Independent environment packages can run real engine and product E2E checks with tamper evidence. Installed and source-checkout local endpoint probes can be narrowed by exact profile identity and by an admitted maximum generation-call budget before any endpoint I/O.

## Safe cached-answer revalidation

A run-loop cache hit is candidate material. It re-enters the current policy, grounding, output-contract, and oracle checks before an answer can accept. A cached candidate cannot directly override a held current answer.

## Runnable independent environment E2E

The engine exposes the `flywheel e2e-journey` command for manifest validation and execution. The included gather-context fixtures cover CLI and MCP adapters with explicit runtime admission and artifact receipts.

The engine also includes `harness.enterprise_envs`. The separate `flywheel-env-service-desk-incident` package exposes the `service_desk_incident_env` import namespace and `service-desk-incident-env` CLI at version 0.1.0. Installing it with `flywheel-verify` 0.6.1 enables deterministic Service Desk incident cases, calibration controls, artifact-root preflight, and tamper verification. If the product is absent, the engine compatibility CLI reports a typed product-missing failure.

## Controlled local endpoint probes

The `flywheel endpoint-gate` command accepts an exact `--profile-id` and an admitted `--max-generation-calls` value from either a package install or a source checkout. The budget covers planned generation calls for that gate invocation. It is not a profile-count cap by itself, and omitting it preserves the legacy unbounded selection path.

Ollama profile rows can carry the configured native JSON-schema final-output capability, and the adapter runtime matrix preserves it for local structured-finalizer admission. Bare wheel installs expose packaged engine commands including `endpoint-gate`; remaining source-checkout passthrough commands still require a checkout.

## Experimental finalizer evidence

The local finalizer experiment records the execution order of experimental arms in the reviewed command path. That record identifies which arm order was tested; it does not turn arm ordering into an answer-quality claim.

## Private artifact roots and borrowed descriptors

`harness.private_artifact_fs` adds private artifact-root controls and a same-process borrowed descriptor context for POSIX file descriptors and Windows handles. Borrowed descriptors are scoped to their context manager lifetime, reject active re-entry, and do not serialize authority. On Linux, private artifact operations admit the opened filesystem before reads, writes, publication and descriptor borrowing. Windows-drive 9p/v9fs mounts under WSL and unclassified filesystems are refused with `UNSUPPORTED_FS`; use native Linux storage for these private artifacts.

## Boundary

The assembled Python suite and desktop tests passed, with unsupported or intentionally excluded cases recorded as skips. These checks do not establish local-model quality uplift, live endpoint results, physical-device acceptance or complete coverage of every product workflow. Installation and published artifacts require separate release verification.
