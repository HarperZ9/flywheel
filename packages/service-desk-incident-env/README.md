# Service Desk Incident Environment

A runnable incident-management environment for testing agent workflows. It owns
its state, action log, verifier and release surface. The cases use synthetic
data and local HTTP services. They do not connect to ServiceNow, StateMachines
or model providers.

## Install from this checkout

Use Python 3.11 or newer in a virtual environment. From the Flywheel repository
root, install the engine and this product:

```sh
python -m pip install . ./packages/service-desk-incident-env
service-desk-incident-env identity --json
```

The product version is 0.1.0. It requires `flywheel-verify>=0.6.1,<0.7`, exposes
the `service_desk_incident_env` Python package and uses environment ID
`service-desk-incident/v1`. It can also be installed from its wheel alongside a
compatible engine wheel. A source directory or wheel download is not evidence
of a PyPI listing.

## Run and verify a workflow

```sh
service-desk-incident-env e2e --out ./incident-runs
```

The command prints JSON containing `artifact_dir`. This is the generated run
directory beneath `incident-runs`, not the parent passed to `--out`. Pass that
exact returned directory to the next commands:

```sh
service-desk-incident-env verify RETURNED_ARTIFACT_DIR --recompute --json
service-desk-incident-env review RETURNED_ARTIFACT_DIR --json
```

For PowerShell, capture it directly:

```powershell
$incidentRun = service-desk-incident-env e2e --out ./incident-runs | ConvertFrom-Json
service-desk-incident-env verify $incidentRun.artifact_dir --recompute --json
```

Verification exits 0 for a passing artifact set and 1 for failed verification.
Missing files and altered recorded state fail verification. Keep the original
run intact when investigating a failure; run a new case into a new output root.
Use `contract --json` and `descriptor --json` to inspect supported actions and
case definitions. Use `doctor --out ./incident-doctor --json` to exercise the
installed product and its artifact verification.

## What the cases establish

The E2E suite covers scripted success, hidden-control denial, malformed input,
concurrent isolation, duplicate-action idempotency, atomic reset and restart
recovery. Its calibration checks expose known invalid submissions. Run receipts
and the review command retain failed cases and their evidence.

These are product and verifier checks against synthetic cases. They do not
measure a model's success rate, establish production ServiceNow compatibility,
or prove that an unseen incorrect submission can never be accepted. Agent
comparisons need separate model runs, held-out tasks and complete cost records.

Write artifacts into a dedicated output directory outside the installed package
or source tree. A rejected artifact root returns a typed failure; do not treat
that refusal as a successful workflow.

## Share a review without changing the evidence

```sh
service-desk-incident-env review RETURNED_ARTIFACT_DIR --html-out ./review-output/review.html --json
```

The optional HTML report uses no scripts, network requests, or external assets.
Its output must be a new file outside the artifact directory. Open it locally
and inspect it before sharing. The JSON response keeps the existing identity,
verification, cases, and calibration fields and adds separate evidence layers.
It contains local paths; the HTML omits those paths and redacts common credential
and local-path strings. This is not comprehensive sensitive-data detection.

The report distinguishes receipt claims, internal digest consistency, task
semantics recomputed by the bounded synthetic oracle, and consistency of recorded
authorization, response, and mutation flags. Verify and review both reject a
record that claims a mutation was applied while authorization was denied or the
response was unsuccessful, even when its digest has been recomputed. Malformed
and missing evidence produces a failure report. Review exits 1 for failed checks;
output errors exit 2. The original recorded cases and calibration cases are shown,
not rerun. No submitted log action is executed.

Matching hashes establish internal consistency, not trusted provenance. A recorded
allowed flag does not establish real authorization. Fabricated coherent state and
logs may satisfy the task oracle and record checks. These checks do not establish
independent ground truth, general agent safety, or production containment.
