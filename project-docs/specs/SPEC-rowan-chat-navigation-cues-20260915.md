# Spec: Rowan chat navigation cue bindings

## Objective

Connect a small set of existing chat navigation actions to the Rowan action cue controller so recorded lines can play from actual user-visible navigation predicates. This is source/runtime wiring only; shell ownership remains with the shell owner and no release, installer, or Python behavior changes are made here.

## Requirements

- [x] Add optional `RowanActionCueController? actionCueController` to `AgentView` and pass the same parameter name through to `ChatWorkspace`.
- [x] Do not edit shell wiring, Studio controllers, Python code, packaging code, or release metadata.
- [x] Fire `chat.bookmark_added` only after a bookmark is actually added to the current conversation. Removing a bookmark stays silent.
- [x] Fire `chat.history_search` only when the user commits a nonempty search. Typing alone and empty submissions stay silent. Rapid repeats rely on the existing controller cooldown.
- [x] Fire `chat.jump_to_source` only from the Links tab source-jump action and only when the chat target resolves in the current conversation.
- [x] Leave notes cues unbound because the current notes field persists on every text change and has no separate durable commit action.
- [x] Keep recovered/history-load paths silent by doing no cue dispatch in initialization or widget update.
- [x] Use deterministic nonsecret event refs that do not expose query text, link URLs, notes, message text, or transcript content.
- [x] Preserve user opt-in, mute, cooldown, replay labeling, and `provesTaskCorrectness: false` through the existing controller.

## Technical Approach

Thread `actionCueController` from `AgentView` into `ChatWorkspace`. `ChatWorkspace` will create stable cue events with generated complete-pack cue constants and call `controller.handle` without awaiting playback. Event refs are short `chat_<sha256-prefix>` values derived from non-content metadata such as action kind, conversation id, message id, target offset, and a local search commit serial. `ChatNavigationPanel` will expose optional callbacks for committed search and link source-jump; the existing target-selection behavior stays unchanged.

## Files to Modify

- `desktop/lib/views/agent_view.dart` — optional controller constructor field.
- `desktop/lib/views/agent_view_layout.dart` — pass controller to `ChatWorkspace`.
- `desktop/lib/widgets/chat_workspace.dart` — cue dispatch for bookmark add, search commit, and resolved link source jump.
- `desktop/lib/widgets/chat_navigation_panel.dart` — committed-search and source-jump callbacks.
- `desktop/test/chat_navigation_cues_test.dart` — focused widget tests for cue predicates.
- `project-docs/specs/SPEC-rowan-chat-navigation-cues-20260915.md` — this receipt.

## Success Criteria

- [x] Focused chat navigation cue tests pass with `C:/flutter/bin/flutter.bat test test/chat_navigation_cues_test.dart`.
- [x] Focused analyzer passes for the touched Dart files or the remaining analyzer output is unrelated and clearly reported.
- [x] File gate remains clean for touched files.
- [x] Final report lists bound and intentionally unbound cases.

## Blockers

None identified. Shell construction of the shared Rowan controller is a follow-on owner task.

## Status: IMPLEMENTED

Root/user directed this bounded implementation on 2026-09-15.
