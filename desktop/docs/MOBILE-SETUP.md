# Mobile setup: the assistant on a phone

This is the last mile for running the app as a phone assistant. The routing,
planning, execution, the accountable agent path, and the panel are already built and
tested in pure Dart; the pieces here are the platform layer, which needs a real
device and a configured toolchain and cannot be verified on a headless CI box.

The app talks to your PC's gateway. Set that up first with the gateway bind seam
(`--host` / `--allow-host`) and a Cloudflare tunnel (see relay's
`docs/REMOTE-SETUP.md` and `scripts/serve_cloudflared.ps1`), then pair the tunnel URL
and token in the app under the rail's connection action.

## What is already done

- `lib/assistant/assistant_router.dart`: `routeIntent` and `planFor`, deterministic
  and offline.
- `lib/assistant/assistant_executor.dart`: `AssistantExecutor`, `AgentSink`,
  `DeviceSink`, and `GatewayAgentSink` (posts a work task to `POST /api/relay/start`).
- `lib/assistant/voice.dart`: `VoiceInput` and `VoiceOutput`, with a `SilentVoice`
  default so a build with no speech engine still types.
- `lib/widgets/assistant_panel.dart`: the panel, with an optional microphone that
  appears only when `VoiceInput.available` is true.

The device build supplies three concrete classes and wires them in. Every class
below implements an interface that already exists, so nothing in the tested core
changes.

## 1. Toolchain

- Android: install Android Studio, then `flutter doctor` until the Android toolchain
  is a check. On Windows, enable Developer Mode (`start ms-settings:developers`) so
  plugin packages can be set up.
- iOS: a Mac with Xcode. `flutter build ipa` does not run on Windows or Linux.

## 2. Add the platform targets

```
cd desktop
flutter create --platforms=android,ios .
```

Web is a separate path: the app currently pulls in `dart:io` and a transitive
`dart:ffi` dependency, neither of which links on the web target, so a PWA build needs
those guarded behind conditional imports first. Native android and ios are the
supported phone builds today.

## 3. Add the packages

In `pubspec.yaml` under `dependencies`:

```yaml
  url_launcher: ^6.3.0
  speech_to_text: ^7.0.0
  flutter_tts: ^4.2.0
```

Then `flutter pub get`.

Permissions:

- Android, in `android/app/src/main/AndroidManifest.xml`:
  ```xml
  <uses-permission android:name="android.permission.RECORD_AUDIO"/>
  <uses-permission android:name="android.permission.INTERNET"/>
  ```
- iOS, in `ios/Runner/Info.plist`:
  ```xml
  <key>NSMicrophoneUsageDescription</key>
  <string>Speak commands to the assistant.</string>
  <key>NSSpeechRecognitionUsageDescription</key>
  <string>Turn your spoken commands into text.</string>
  ```

## 4. The concrete device sink

`lib/assistant/url_device_sink.dart`. It launches the maps and music links a plan
produces, and reports honestly for the internal media and timer actions, which need
platform channels (a media session, a local notification) rather than a URL.

```dart
import 'package:url_launcher/url_launcher.dart';
import 'assistant_executor.dart';

class UrlLauncherDeviceSink implements DeviceSink {
  UrlLauncherDeviceSink({Future<bool> Function(Uri)? launcher})
      : _launch = launcher ??
            ((uri) => launchUrl(uri, mode: LaunchMode.externalApplication));

  final Future<bool> Function(Uri) _launch;

  @override
  Future<bool> open(String deepLink) async {
    final uri = Uri.tryParse(deepLink);
    if (uri == null) return false;
    if (uri.isScheme('http') || uri.isScheme('https')) return _launch(uri);
    // media: and timer: are internal actions handled by platform channels, not a
    // URL launch, so report not-yet-handled rather than pretending to open them.
    return false;
  }
}
```

## 5. The concrete voice engine

`lib/assistant/speech_voice.dart`. A thin wrapper over `speech_to_text` and
`flutter_tts` behind the `VoiceInput` and `VoiceOutput` interfaces.

```dart
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'voice.dart';

class SpeechVoiceInput implements VoiceInput {
  final SpeechToText _stt = SpeechToText();
  bool _ready = false;

  @override
  bool get available => true;

  Future<void> init() async {
    _ready = await _stt.initialize();
  }

  @override
  Future<String?> listen() async {
    if (!_ready) await init();
    if (!_ready) return null;
    final done = Completer<String?>();
    await _stt.listen(
      onResult: (r) {
        if (r.finalResult) done.complete(r.recognizedWords);
      },
      listenFor: const Duration(seconds: 8),
    );
    return done.future;
  }
}

class FlutterTtsVoiceOutput implements VoiceOutput {
  final FlutterTts _tts = FlutterTts();

  @override
  Future<void> speak(String text) => _tts.speak(text);
}
```

Add `import 'dart:async';` for the `Completer`.

## 6. Wire them in

In `lib/shell/flywheel_shell.dart`, where `onOpenAssistant` builds the executor,
swap the placeholder device sink for the launcher and pass the voice engine:

```dart
onOpenAssistant: () => showAssistantPanel(
  context,
  executor: AssistantExecutor(
    agent: GatewayAgentSink(_dependencies.client),
    device: UrlLauncherDeviceSink(),
  ),
  voiceInput: _voiceInput,   // a SpeechVoiceInput on the phone build
  voiceOutput: _voiceOutput, // a FlutterTtsVoiceOutput on the phone build
),
```

Build the two voice objects once in the shell state (a `SpeechVoiceInput` and a
`FlutterTtsVoiceOutput`), so the microphone appears and the reply is spoken. On a
desktop build, leave them as `SilentVoice` and the panel stays typed-only.

## 7. Build and run

```
flutter run                 # on a connected device or emulator
flutter build apk           # a release Android build
flutter build ipa           # a release iOS build, on a Mac
```

## What each command does on the phone

- "fix the failing test" starts a witnessed run on your PC through the gateway, and
  the reply and run id come back to the phone. The receipts travel with it.
- "navigate to the airport" opens the maps app with directions.
- "play some jazz" opens the music app to that search.
- "set a timer for 5 minutes", "pause", "skip" route to device actions; the timer
  and media transport controls are the ones that still need a platform channel, per
  the device sink note above.
