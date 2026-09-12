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
authorized. Cutting a version and publishing its assets stay gated until the word
is given. The word was given for the `v0.6.2` installer, which is now attached
with a verified receipt (item 1). The 1.0.0 cut is a separate decision and stays
gated.

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
| Windows installer on the latest release | DONE | `Flywheel-Setup-0.6.2-x64.exe` + `SHA256SUMS.txt` attached to v0.6.2, hash verified; see below |
| Chat draft store failure classification | DONE | read failure is now a distinct kind; #230 on `main` |
| STATE.md caught up to `main` | DONE | five releases narrated, v0.4.1 through v0.6.2 |
| The 1.0.0 cut | GATED | production deploy; needs explicit "yes, deploy" |
| Attaching an installer to a release | DONE | operator authorized; done for v0.6.2, hash verified end to end |

## Closed item 1: the installer is attached to the latest release

Verified 2026-09-12. The operator authorized the publish, and the Windows
installer now sits on `v0.6.2` with its hash receipt. `GETTING-STARTED.md` sends
a desktop user to the release page to download `Flywheel-Setup-<version>-x64.exe`
and verify it against the release's `SHA256SUMS.txt`. That path now works for the
current release.

Assets now on `v0.6.2`:

- `Flywheel-Setup-0.6.2-x64.exe` (26,445,373 bytes).
- `SHA256SUMS.txt`, naming that exe with SHA-256
  `dad5d9a07c3bfb5b453792aa0ccb07fa546adba1d336c8271ff005d7602bd1cd`.
- `frozen-gateway-smoke.json`, the engine freeze receipt.

How it was published. The installer came from the `windows-installer-candidate`
artifact that `desktop-release.yml` staged for the `v0.6.2` tag run, a build from
the tag's own commit behind the version gate (tag == pubspec == pyproject), the
frozen-gateway smoke check, `flutter analyze`, and `flutter test`. Its hash was
recomputed off the downloaded exe and matched the receipt, then the exe was
re-downloaded from the live release and matched the receipt again. This is the
by-hand attach, run once under an explicit operator authorization.

The attach kept the two-stage control intact. `desktop-release.yml` still holds
`contents: read`, still builds a candidate with a hash receipt, and still never
touches a Release. There is no `gh release upload` step in the `installer` job,
and that absence is the design. `windows-publish.yml` is still the only workflow
with a publish path: `on: workflow_call:` only, its own permission still
`contents: read`, the write capability arriving through an explicit
`publish_token` secret a caller has to pass, an existing asset a hard no-clobber
failure. Nothing in the repository calls it, and the by-hand attach did not
change that. The publish above was `gh release upload` run against `v0.6.2` by a
person holding the authorization, not a workflow, so no build gained the power to
publish.

What is left, and who owns it. Wiring the publish as its own gated step that
calls `windows-publish.yml` via `uses:` is still not done. It is a release-path
and security-posture change the operator owns, and it cannot be run to green in
this environment. It is not a 1.0 blocker: a 1.0.0 release can be published by
hand the same way this one was, or the wiring can land first so the cut does not
repeat the manual attach. The choice is the operator's.

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

Keep the 1.0.0 cut gated. Every logged readiness item is now closed. The chat
draft store fix landed in #230, the STATE.md catch-up across the five releases is
done, and the Windows installer is attached to `v0.6.2` with a verified receipt.
Nothing on the readiness list is waiting.

One optional piece of housekeeping is left, and it is not a blocker: wiring the
publish path so a future cut does not need a by-hand attach. That is a
release-path and security-posture change the operator owns.

When the operator says deploy, the 1.0.0 cut is a clean promotion of what is
already on `main`, not a scramble. The product is honest about what it is at
0.6.2 already. The gate is about the version label and the release ceremony, not
about hidden work.
