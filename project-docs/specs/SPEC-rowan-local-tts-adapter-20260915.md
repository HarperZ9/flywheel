# Spec: Rowan local TTS service adapter

## Objective

Build a private, optional Rowan text-to-speech prototype that can render local
Qwen3-TTS VoiceDesign WAV files behind Flywheel's existing `VoiceOutput`
interface, without touching the verifier accept path or wiring the desktop shell.

## Requirements

- [x] Keep the Python service under `desktop/tool`, outside the packaged harness
  accept path.
- [x] Bind the daemon to loopback only and require a bearer token.
- [x] Use bounded JSON bodies, text length, queue depth, and one synthesis worker.
- [x] Load the Qwen model lazily and keep it resident after the first real job.
- [x] Preserve cancellation semantics for queued jobs and truthfully report that
  running Qwen generation is not interrupted mid-call.
- [x] Make stop revocation atomic with request acceptance, job registration, and
  queue insertion, so a pending request cannot create an orphan queued job after
  stop.
- [x] Write per-job provenance for text, model repo, model revision, prompt,
  generation settings, timing, GPU snapshots, WAV path, and WAV hash.
- [x] Keep Rowan's tone profile adjustable and avoid locking a final voice while
  the user is still choosing an accent direction.
- [x] Add a Dart `VoiceOutput` adapter that can submit to the local service later
  without changing shell composition now.
- [x] Test auth, loopback checks, queue bounds, queued cancellation, stop behavior,
  and Dart request construction.

## Technical Approach

Add a small stdlib HTTP service package in `desktop/tool/rowan_tts`. The service
offers `/v1/health`, `/v1/speak`, `/v1/jobs/<id>`, `/v1/jobs/<id>/audio`,
`/v1/jobs/<id>/cancel`, and `/v1/stop`. A fake WAV backend supports fast unit
tests. The Qwen backend imports torch and qwen_tts only when selected and loads
from a caller-supplied local model directory with Hugging Face offline flags and
`local_files_only=True`.

Add `desktop/lib/assistant/local_tts_voice.dart`, an optional `VoiceOutput`
implementation that enforces loopback base URLs, sends bearer auth, submits text
to `/v1/speak`, and can wait for the generated WAV receipt. The existing shell
will not be modified.

## Files to Modify

- `desktop/tool/rowan_tts/*.py` for the service runtime.
- `desktop/tool/rowan_local_tts_service.py` for a CLI entrypoint.
- `desktop/lib/assistant/local_tts_voice.dart` for the optional Dart adapter.
- `tests/test_rowan_local_tts_service.py` for Python service contract tests.
- `desktop/test/local_tts_voice_test.dart` for Dart adapter tests.
- `project-docs/specs/SPEC-rowan-local-tts-adapter-20260915.md` for this receipt.

## Success Criteria

- [x] Python service tests pass without loading Qwen.
- [x] Dart adapter test passes with a mock HTTP client.
- [x] File gate passes for new files.
- [x] A real local Qwen request succeeds from the service using the cached model.
- [x] A queued job can be cancelled before synthesis.
- [x] A missing-job cancel reports failure without crashing.
- [x] A delayed `/v1/speak` request that finishes validation after `/v1/stop`
  returns `503 SERVICE_STOPPING` rather than `202` with a queued orphan.
- [x] Final report states that generated WAVs are full-buffer outputs, not
  streaming or real-time speech.

## Blockers

None identified.

## Measurement receipt

The private measurement receipt is stored outside this worktree in the local
mission archive.

The measured real request used the cached Qwen3-TTS VoiceDesign revision
`5ecdb67327fd37bb2e042aab12ff7391903235d3` with Hugging Face offline flags,
completed one full-buffer WAV, rejected a third request with `QUEUE_FULL`,
cancelled a queued job, returned `JOB_NOT_FOUND` for a missing cancel, and was
later repaired so delayed pending `/v1/speak` requests cannot be accepted after
stop revocation.

## Status: IMPLEMENTED AND MEASURED
