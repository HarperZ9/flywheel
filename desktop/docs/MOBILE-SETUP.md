# Flywheel on a phone

Run the same app on Android and reach the engine on your PC over your own
tunnel. You speak or type a command, the run happens on your machine, and the
receipts come back to the phone. Nothing about the verification changes because
the screen got smaller.

The Android target is built and the release build produces an APK. iOS needs a
Mac and has not been created yet; that gap is stated at the bottom rather than
hidden.

## 1. Point the phone at your engine

The app talks to your PC's gateway, which binds to localhost by default and
stays there unless you widen it. Two flags open it, and both are explicit:

```bash
python -m harness.cli_entry gateway --host 0.0.0.0 --allow-host your-tunnel.example.com
```

Then put a tunnel in front of it. Relay's `docs/REMOTE-SETUP.md` and
`scripts/serve_cloudflared.ps1` set up a Cloudflare tunnel end to end. Pair the
tunnel URL and the gateway token in the app under the rail's connection action.
The token is stored on the device and is never sent anywhere but your gateway.

## 2. Build it

```bash
cd desktop
flutter run                 # a connected device or emulator
flutter build apk --release # a release APK at build/app/outputs/flutter-apk/
```

`flutter doctor` should show the Android toolchain as a check first. On Windows
turn on Developer Mode (`start ms-settings:developers`) so plugin packages set
up correctly.

### Signing

The release build looks for `android/key.properties`. Copy
`android/key.properties.example`, generate a keystore, and fill it in:

```bash
keytool -genkey -v -keystore flywheel-release.jks -keyalg RSA -keysize 2048 -validity 10000 -alias flywheel
```

The keystore and that file are gitignored and never belong in the repository.

Without `key.properties` the build still runs and the APK still installs, but
it is signed with the debug key and cannot be distributed. Gradle says so
during the build rather than letting a debug-signed APK pass for a release.

The application id is `io.github.harperz9.flywheel`.

## 3. What the phone can do

- "fix the failing test" starts a witnessed run on your PC through the gateway.
  The reply and the run id come back to the phone, and the receipts travel with
  them.
- "navigate to the airport" opens the maps app with directions.
- "play some jazz" opens the music app to that search.
- "set a timer for 5 minutes", "pause", "skip" route to device actions. The
  timer and the media transport controls still need a platform channel, so the
  device sink reports them as unhandled rather than pretending to run them.

The microphone appears only where a speech engine exists. On desktop the panel
stays typed-only, which is a real difference and not a missing feature.

## How it is put together

The routing, the planning, the execution, and the accountable agent path are
pure Dart and are tested without a device:

- `lib/assistant/assistant_router.dart`: `routeIntent` and `planFor`,
  deterministic and offline.
- `lib/assistant/assistant_executor.dart`: `AssistantExecutor`, `AgentSink`,
  `DeviceSink`, and `GatewayAgentSink`, which posts a work task to
  `POST /api/relay/start`.
- `lib/assistant/voice.dart`: the `VoiceInput` and `VoiceOutput` interfaces,
  with a `SilentVoice` default so a build with no speech engine still types.
- `lib/widgets/assistant_panel.dart`: the panel itself.

The device layer implements those interfaces and nothing in the tested core
changes when it is swapped:

- `lib/assistant/url_device_sink.dart`: `UrlLauncherDeviceSink` opens maps and
  music links and returns false for the internal media and timer actions.
- `lib/assistant/speech_voice.dart`: `SpeechVoiceInput` and
  `FlutterTtsVoiceOutput` over `speech_to_text` and `flutter_tts`.
- `lib/shell/flywheel_shell.dart` selects the speech pair on Android and iOS
  and `SilentVoice` everywhere else.

Permissions are declared in `android/app/src/main/AndroidManifest.xml`:
`INTERNET` to reach the paired gateway and `RECORD_AUDIO` to hear a spoken
command. The `queries` block declares the http, https and speech-recognizer
intents that Android 11 and later require for `url_launcher` and
`speech_to_text` to see anything.

## Not done

- **iOS.** No `ios/` target exists. Creating it and building an `.ipa` needs a
  Mac with Xcode, plus `NSMicrophoneUsageDescription` and
  `NSSpeechRecognitionUsageDescription` in `Runner/Info.plist`. Nothing in the
  Dart layer blocks it.
- **Web.** The app pulls in `dart:io` and a transitive `dart:ffi` dependency,
  neither of which links on the web target, so a PWA build needs those behind
  conditional imports first.
- **The media and timer platform channels.** A media session and a local
  notification, per the device sink note above.
