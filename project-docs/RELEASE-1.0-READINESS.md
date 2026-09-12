# Flywheel release 1.0 readiness

> Internal register. This is not a public surface. It uses local paths, gate
> language, and PR numbers on purpose. Public copy lives in `README.md`,
> `GETTING-STARTED.md`, and `project-docs/releases/`. Read
> [PROJECT.md](../PROJECT.md) first for the whole picture, then
> [STATE.md](STATE.md) for the running cursor.

Last updated: 2026-09-12.

## Where this stands

`main` is 0.6.2. A 1.0.0 cut is a major-version release, and a major-version
release is a production deploy, so it stays gated on an explicit "yes, deploy"
from the operator. Nothing here cuts it. This file records what is ready, what
is open, and what is gated, so the decision has ground under it when the
operator wants to make it.

Readiness work is normal development. Merging a docs or code PR to `main` is
authorized. Cutting the release, attaching an installer to a release, and
publishing to PyPI are not, until the word is given.

## Version reality (verified 2026-09-11)

- `pyproject.toml` version 0.6.2; `desktop/pubspec.yaml` version 0.6.2+17.
- Latest published GitHub release: Flywheel 0.6.2 (tag `v0.6.2`, 2026-09-11).
- Release tags in order: `v0.4.1`, `v0.5.0`, `v0.6.0`, `v0.6.1`, `v0.6.2`.
- 137 commits from `v0.4.0` to `origin/main`.
- The STATE.md cursor now narrates all five releases from `v0.4.1` through
  `v0.6.2`, each with a dated entry. The earlier five-release lag from `v0.4.0`
  is closed.

## What shipped since 0.4.0

Each engine release carries a doc under `docs/` (`docs/RELEASE-<version>.md`).

| Tag | Date | Subject |
|---|---|---|
| v0.4.1 | 2026-09-07 | exact hook grants and evidence resources |
| v0.5.0 | 2026-09-08 | native continuation, Bulletin identity, and bounded execution |
| v0.6.0 | 2026-09-08 | native continuation and durable repository mapping |
| v0.6.1 | 2026-09-09 | E2E environments and controlled endpoint probes |
| v0.6.2 | 2026-09-11 | Rowan operation and the native provider protocol |

Rowan reached `main` across three merges:

- [#221](https://github.com/HarperZ9/flywheel/pull/221) grew the first-run
  launch walkthrough into a nine-step feature tour. Merged `f3450d70`.
- [#222](https://github.com/HarperZ9/flywheel/pull/222) gave Rowan a spoken
  voice persona: soft male, Australian or English accent, lowered pitch and
  pace. Merged `3dc5a0a6`. Spoken output is mobile-only today. The desktop
  client stays silent and there is no distributed phone build, so the spoken
  line is held out of desktop-facing intro docs as an honest null.
- [#223](https://github.com/HarperZ9/flywheel/pull/223) introduced Rowan in the
  public intro docs, which had no mention of the assistant anywhere. Merged
  `9a74018d`.

## Readiness ledger

| Item | State | Note |
|---|---|---|
| Engine on PyPI (`flywheel-verify`) | DONE | 0.6.2 wheels and sdists attached to the release |
| Public intro docs name Rowan | DONE | #223 on `main` |
| First-run tour | DONE | nine steps, #221 on `main` |
| Rowan voice matches the Codex spec | DONE | #222 on `main` |
| Windows installer on the latest release | OPEN | absent from v0.6.1 and v0.6.2; see below |
| Chat draft store failure classification | DONE | read failure is now a distinct kind; #230 on `main` |
| STATE.md caught up to `main` | DONE | five releases narrated, v0.4.1 through v0.6.2 |
| The 1.0.0 cut | GATED | production deploy; needs explicit "yes, deploy" |
| Attaching an installer to a release | GATED | a publish; needs the word |

## Open item 1: the installer is missing from the two latest releases

Verified 2026-09-11.

The release page is where `GETTING-STARTED.md` sends a desktop user. Its "Start
the desktop client" step reads: download `Flywheel-Setup-<version>-x64.exe` from
the releases page and verify it against the release's `SHA256SUMS.txt`. For the
current release that file is not there.

Assets actually attached:

- `v0.6.0`: `Flywheel-Setup-0.6.0-x64.exe` (25,587,795 bytes), `SHA256SUMS.txt`,
  `frozen-gateway-smoke.json`.
- `v0.6.1`: Python wheels and sdists only. No installer, no `SHA256SUMS.txt`.
- `v0.6.2`: Python wheels and sdists only. No installer.

Mechanism. `.github/workflows/desktop-release.yml` triggers on `push` of a `v*`
tag and on `workflow_dispatch`. It has one job, `installer`, on
`windows-latest`. That job builds the installer, computes the SHA-256, writes
`SHA256SUMS.txt`, and uploads all of it as a GitHub Actions artifact named
`windows-installer-candidate` with a 14-day retention. That job holds
`contents: read` and never touches a GitHub Release. Its header says so
outright: the build stages a candidate with a hash receipt, and publishing is a
separate operation. There is no `gh release upload` step, and that absence is
the design.

`.github/workflows/windows-publish.yml` is the only workflow that publishes, and
it is deliberately hard to reach. It is `on: workflow_call:` only, its own
repository permission is still `contents: read`, and the write capability
arrives through an explicit `publish_token` secret the caller has to pass. An
existing release or asset is a hard no-clobber failure. Nothing in the
repository calls it today. The one reference in `desktop-release.yml` is a
comment on line 6, not a `uses:` invocation.

So attaching the `.exe` to a release is a manual step today: download the
candidate artifact, attach it to the release. That happened for `v0.6.0`. It did
not happen for `v0.6.1` or `v0.6.2`. The 14-day artifact retention means the
`v0.6.1` candidate is close to expiry or already gone, so the byte-identical
artifact may need a rebuild rather than a re-attach.

What to do, ranked. The split between the read-only builder and the write-only
publisher is a deliberate control, so any wiring has to keep the two stages
apart. Do not add a `gh release upload` step to the `installer` job: that job
runs `contents: read` on purpose, and giving it release-write to reach the
installer would fold the two stages into one and hand every tagged build the
power to publish.

1. Wire the publish as its own gated step that calls `windows-publish.yml` via
   `uses:`, passing the tag, the candidate's verified SHA-256, and a
   fine-grained `publish_token`. Keep the trigger explicit, a
   `workflow_dispatch` or a manual approval, so a tag push still only builds a
   candidate and a person still authorizes the publish. This is a release-path
   and security-posture change the operator owns, and it cannot be run to green
   in this environment. Land it, then tag a point release to exercise it before
   relying on it for 1.0.0.
2. Until that wiring lands, attach an installer to the release the docs point at
   by hand, so the current instruction is not broken. Download the candidate
   artifact, verify its hash against `SHA256SUMS.txt`, and attach both. This is
   a publish, so it is gated.

## Closed item 2: the chat draft store classifies a read failure distinctly

Fixed in [#230](https://github.com/HarperZ9/flywheel/pull/230), merged
`59581777`. Ran to green before merge: `flutter analyze` clean, and
`flutter test test/chat_draft_test.dart` at 11 passing.

Root cause. `desktop/lib/services/chat_draft_store.dart`, `load()`. One `try`
wrapped the file read (`readJourneyLocalObject(storageFile)`) and the decode and
validation after it, and a single `catch (_)` mapped every failure to
`ChatDraftFailure.corruptStore`. An OS or FFI read error on intact bytes got the
same kind as bytes that were actually corrupt.

The fix. `load()` now catches `on FileSystemException` first and throws a new
`ChatDraftFailure.readFailed`, and it keeps `corruptStore` for a real decode or
validation failure. The read primitive splits cleanly. `lengthSync()` and
`readAsBytesSync()` are the points that throw `FileSystemException`, a bad record
throws a domain exception, and malformed bytes throw `FormatException`, so the
new clause catches read failures and nothing else. Two tests cover it: an
unreadable store behind a failing `File` asserts `readFailed`, and corrupt bytes
still assert `corruptStore`.

Scope, checked on both draft stores. The wrong label was latent, and it stays
latent across the family. No consumer branches on the chat store's failure kind.
The code draft store was read too. The only catcher of `CodeDraftStoreException`
is `code_view.dart`, and both catch sites there use `catch (_)` and drop the
kind, so its own read-against-corrupt lumping is latent as well and needs no
change now. Its user-facing recovery notices come from a separate
`recoveryOutcomes` path, not from the failure kind. This corrects the earlier
note here, which had read the code store's internal remap as a live consumer of
the kind. The 1.0 reasoning holds for both stores.

## Recommendation

Keep the 1.0.0 cut gated. The readiness item left open does not need a major bump
to close. It lands as normal development on `main` and ships in a 0.6.x point
release:

- Installer-publish path wired, and an installer attached to the release the
  docs point at. The wiring is a release-path change and the attach is a publish,
  so both stay with the operator.

The chat draft store fix landed in #230, and the STATE.md catch-up across the
five releases is done. Only the installer publish is left, and it is gated.

When that is closed and the operator says deploy, the 1.0.0 cut is a clean
promotion of what is already on `main`, not a scramble. The product is honest
about what it is at 0.6.2 already. The gate is about the version label and the
release ceremony, not about hidden work.
