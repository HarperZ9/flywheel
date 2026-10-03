# Reconciliation before the monitor/outcome sidecar

Recorded September 23, 2026 UTC, at the start of the BlueDot task-bundle
workstream. This is task T0 from that bundle: reconcile active work, release
ownership and baseline before writing anything. It is a reconciliation record,
not a release receipt and not a claim that any gate is cleared.

## What the snapshot claimed, and what is live

The bundle's `LIVE-STATE.md` was taken September 22 PDT. Every fact in it that
bears on ownership was rechecked against the live repository on September 23 and
matched exactly:

| fact | snapshot | live | agrees |
|---|---|---|---|
| `origin/main` | `91dfd406d` | `91dfd406d` | yes |
| working branch | `fix/windows-ci-subprocess-cold-start-timeouts` | same | yes |
| working HEAD | `4c9458f48` | `4c9458f48` | yes |
| dirty files | 3 generated Flutter files, `relay` | same four | yes |
| `pyproject.toml` | 1.0.3 | 1.0.3 | yes |
| `desktop/lib/version.dart` | 1.0.3 | 1.0.3 | yes |
| `desktop/pubspec.yaml` | 1.0.3+22 | 1.0.3+22 | yes |

`origin/main` at `91dfd406d` is "Enable every published lane, align every version
with the index (#283)", merged earlier in the same session that received this
bundle. The snapshot and the active work describe the same repository state.

## Release state, reconciled

The bundle asks for the release discrepancy to be resolved before anything else.
Resolved as follows, from the registry and the forge rather than from documents
or tags alone.

**Two different artifacts were being conflated.** `flywheel-verify` on PyPI and
the Flywheel desktop platform candidate are separate release tracks with separate
obligations. `docs/RELEASE-1.0.0.md` describes the desktop candidate: Windows
packaging, installed acceptance on candidate bytes, Android/Relay/Plexus handoff.
Its holds are about that artifact.

**Observed, September 23:**

- PyPI `flywheel-verify` latest is **1.0.2**. Released: 1.0.0, 1.0.1, 1.0.2.
- GitHub releases: latest is **v1.0.1**. A `v1.0.2` tag exists with no GitHub
  release attached to it.
- Local tags: `v1.0.0`, `v1.0.1`, `v1.0.2`. **No `v1.0.3` tag.**
- Source declares **1.0.3** in all three version files.
- `docs/RELEASE-1.0.0.md` still reads `Status: UNRELEASED CANDIDATE`.

**Therefore:** 1.0.3 is declared in source and has never been tagged or
published. `.github/workflows/publish.yml` publishes to PyPI on a v-prefixed
tag, so pushing `v1.0.3` would publish. That is a release action and is not
authorized by this bundle. No tag is pushed by this workstream.

**Unresolved and left for the owner**, recorded rather than acted on:

1. `docs/RELEASE-1.0.0.md` says do not tag or publish 1.0.0 until nine holds
   clear, and `v1.0.0` was tagged and `flywheel-verify` 1.0.0 published. Either
   the holds were cleared without the document being updated, or the document's
   scope is narrower than its wording. The document does not say which.
2. `v1.0.2` has a tag and a PyPI release but no GitHub release.
3. The nine holds are written against 1.0.0. If they remain open they belong on
   the current track, which is 1.0.3. Carrying them forward is an owner decision.

This workstream does not restart, downgrade, retag or re-declare any release. It
adds no dependency to the release's critical path.

## Ownership and isolation

The working checkout at `C:/dev/public/flywheel` is left exactly as found: branch
`fix/windows-ci-subprocess-cold-start-timeouts`, HEAD `4c9458f48`, four dirty
files, not switched, cleaned, reset or written to.

This workstream owns one new worktree, `feat/monitor-outcome-sidecar`, created
from `origin/main` at `91dfd406d`. That is the same revision the bundle's
LinuxArena dossier pinned when it inspected the importer, so the dossier's
source claims and this branch describe the same code.

`D:/fw-industry-response-20260912/inspect-scorer-units` is present and is
recorded as frozen by the workspace canon. It is not touched.

Open pull requests `#282` and `#275` are owned elsewhere and are not modified.

## Baseline and decision criteria, recorded before evaluating

Predeclared here so a later result cannot be fitted to them.

**Decision this work is meant to inform.** Whether Flywheel should carry monitor
judgments from an Inspect/Control Tower evaluation alongside independently
verified task outcomes, in a form a reviewer can replay.

**Baseline.** Today the importer preserves evaluation structure and explicitly
retains `semantic_verification: UNVERIFIABLE`. Monitor scores and verified
outcomes are not carried as distinct, separately checkable quantities.

**Change trigger.** Adopt a sidecar only if it can hold a monitor judgment and an
independent outcome apart, across the three documented Inspect monitor shapes,
and refuse to turn a missing or unscored monitor value into zero or success.
Show that by failing controls that are built to be wrong.

**What would make this not worth adopting.** If the existing importer already
preserves monitor extensions losslessly, a sidecar adds a layer for nothing. The
dossier flags this as untested: "First test nested monitor-score compatibility;
do not assume the existing importer preserves every extension." That test comes
before the design is committed to.

## Claims this record supports

Observed: the repository state, the registry state, the tag state, and the
document text quoted above. Inferred: nothing. Proposed: the sidecar design and
its acceptance criteria. Unknown: whether the nine holds are open, which only the
owner can settle.

Does not prove: that any release gate is cleared, that any artifact is installed
or adopted, or that a monitor detects anything. No evaluation has been run.
