# Spec: Rowan complete action cue pack integration

## Objective

Package the completed Rowan recorded cue library into the desktop app so runtime cue lookup can address the full 186-clip manifest while preserving the existing 48 cue APIs and playback safeguards. This change prepares app-level clip support only; product controllers will bind new events in follow-on work.

## Requirements

- [x] Copy the completed pack manifest and all 186 WAV assets into `desktop/assets/rowan/action-cues/cartesia-rowan-complete-pack` with no local private paths, provider credits, or receipts packaged as runtime assets.
- [x] Update Flutter asset packaging so the complete pack is bundled exactly once.
- [x] Generate Dart clip records from the copied manifest, retaining transcript text, text hash, audio hash, category, trigger, source pack, generation state, and provenance basis for every clip.
- [x] Preserve existing `RowanActionCueKind.<oldCue>` APIs for the prior 48 cue IDs.
- [x] Add string-backed complete-pack cue IDs so the 138 additional manifest events can be selected without a 186-case switch.
- [x] Keep cue selection deterministic and hash-bound by event ID, event ref, and available variant IDs.
- [x] Preserve opt-in, mute, cooldown, recovered-event suppression, replacement stop, cancellation, recorded caption, and `provesTaskCorrectness: false` behavior.
- [x] Keep all modified Dart source files under the 300-line gate.
- [x] Do not modify shell wiring, Studio controllers, external provider routes, release metadata, or install/release state.

## Technical Approach

Use the complete-pack manifest as the app source of truth. Copy the manifest and WAV files into a single app asset pack, point `pubspec.yaml` at that pack's `audio/` directory, and generate sharded Dart clip-data maps from manifest rows. Convert the cue-kind representation from an enum into a const, string-backed value class with the same static constants for the old 48 IDs. Add a generated lookup of all manifest event IDs to provide typed complete-pack factories and metadata without a sprawling switch. The controller and registry will select clips by the string-backed cue ID, so old automatic bindings keep working and follow-on product bindings can create manifest-backed events from generated cue constants.

## Files to Modify

- `desktop/assets/rowan/action-cues/cartesia-rowan-complete-pack/**` — copied manifest and 186 audio assets.
- `desktop/pubspec.yaml` — package the complete pack audio directory once.
- `desktop/lib/assistant/rowan_action_cue_models.dart` — string-backed cue kinds and complete-pack cue constants.
- `desktop/lib/assistant/rowan_action_cue_clip_model.dart` — retain complete-pack provenance fields.
- `desktop/lib/assistant/rowan_action_cue_clips.dart` — registry lookup against generated complete-pack data.
- `desktop/lib/assistant/rowan_action_cue_pack_provenance.dart` — complete-pack schema, hash, voice, and playback boundary constants.
- `desktop/lib/assistant/rowan_action_cue_complete_ids*.dart` and `rowan_action_cue_clip_data_*.dart` — generated data from manifest.
- `desktop/test/rowan_action_cue_complete_pack_test.dart` and focused existing Rowan cue tests — packaging, lookup, old API preservation, deterministic selection, and safety behavior.

## Success Criteria

- [x] Manifest and audio counts match 186 clips and every packaged WAV hash matches the manifest.
- [x] New complete-pack events such as `onboarding.welcome` and recorded reactions resolve to clips through the registry.
- [x] Existing old cue APIs still resolve and controller tests continue to exercise opt-in, mute, cooldown, recovered-event suppression, cancellation, and replay labeling.
- [x] Generated data files and modified Dart files are under 300 lines.
- [x] Focused Rowan tests, full Flutter tests, analysis and Windows compilation passed in the integration checkout using the configured Flutter executable. Installed playback remains a separate acceptance requirement.
- [x] Final report states only source/runtime support, not release, install, broad product wiring, or all future voice coverage.

## Blockers

None identified. Follow-on product bindings need shell/Studio/controller owners after this runtime support lands.

## Status: IMPLEMENTED AND LOCALLY VALIDATED, INSTALLED ACCEPTANCE PENDING

Root/user directed this exact integration on 2026-09-15 and asked not to pause for new auditions or questions.
