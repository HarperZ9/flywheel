# Desktop spoken replies

Status: implemented locally; independent review, release and installed acceptance remain open.

Rowan reads completed answers from desktop Chat after the user enables Speak
replies. The switch, current state, mute and Stop share the chat header so the
first Send action remains visible at the tested desktop sizes. Typed chat
remains available when speech fails.

Windows and macOS use the existing flutter_tts 4.2.5 package and installed
voices selected by RowanVoiceProfile. Linux displays Unavailable. This change
adds no dependencies, microphone access, external voice service or local daemon.
The installed voice determines the sound; matching Rowan's preferred accent
and voice is best effort.

Speech starts off whenever Chat opens. Opt-in applies to new turns, never
restored history or a turn already in progress. Only assistant content from
a completed stream carrying a receipt is eligible. Tool-call payloads are
excluded. A receipt permits playback; it does not establish answer correctness.

New prompts, conversation changes, agent mode, leaving Chat, backgrounding,
engine disconnect, mute, disable and Stop invalidate queued speech and stop
playback. Epoch checks reject late completions. Native voice setup is shared
across cancelled turns so an old setup cannot overtake a later one. Failed
setup can retry on the next eligible reply.

Replies longer than 12,000 characters stay in typed chat without playback.
Playback has a four-minute deadline and a three-second stop deadline. A
reached limit or failed stop is shown in the header. An unconfirmed stop blocks
the next queued reply. Device diagnostics are not copied into the UI.

Validation commands, run from desktop/:

- flutter test --no-pub test/desktop_speech_controller_test.dart test/desktop_native_voice_test.dart test/desktop_speech_chat_test.dart
- flutter test --no-pub test/agent_mode_split_test.dart test/chat_draft_test.dart test/chat_context_lifecycle_test.dart test/desktop_speech_chat_test.dart
- flutter analyze --no-pub
- flutter test --no-pub

The 28 focused checks passed with fake speech engines. They cover actual chat
event binding, opt-in, history and partial-response silence, tool payloads,
duplicate receipts, cancellation races, setup retry, deadlines and failure
fallback. Send remains directly clickable at 800 by 600 and 1200 by 600 with
speech on, off and unavailable; a 450-pixel-wide failure case has no overflow.
The 46 affected chat checks passed before the four layout cases were added.
Existing chat test helpers remain unchanged. Flutter analysis found no issues.
The full desktop suite passed 1,579 tests with 8 skips. That run started before
the final stale-event guard was added, so it does not verify the entire final
tree unchanged. After that guard, the 17 speech widget tests passed again and
Flutter analysis remained clean.

No speakers were activated. Plugin registration and passing fake tests establish
wiring and simulated behavior, not audible output, voice quality, native stop
reliability or target-device latency. Before release, check installed Windows
and macOS builds for opt-in playback of an actual chat answer, each interruption
path, missing voices, engine refusal and the time limit. Confirm Linux shows
unavailable while typed chat works. Keep release acceptance open until those
device checks have receipts.
