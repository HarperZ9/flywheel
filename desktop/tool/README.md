# Bulletin media decoder runner

`run_bulletin_media_decoder_smoke.ps1` is the product-host Windows decoder gate for the native Bulletin media review path. It launches the Flutter Windows app and verifies real `VideoPlayerController.file` behavior, not widget fakes.

Prerequisites:

- Windows Flutter desktop support and a runnable `flutter` command on PATH, or pass `-FlutterPath` with the executable path such as `C:/flutter/bin/flutter.bat`.
- `nuget.exe` on PATH, or pass `-NuGetPath` with a verified portable NuGet CLI. The script uses the path only for the current process and does not install packages globally or mutate user PATH.
- A generated Windows build directory may retain an unsafe default install prefix. The runner repairs an existing `build/windows/x64` cache by running:
  `cmake -S windows -B build/windows/x64 -DCMAKE_INSTALL_PREFIX=<desktop>/build/windows/x64/runner/Debug`

The runner creates a unique validation directory under the OS temp directory when `-ValidationDir` is omitted. It writes a fresh random `run_id` into the Dart integration test and validates that the receipt echoes that same id before accepting success. A zero-exit Flutter run with a missing, stale, wrong-fixture, or malformed receipt fails the script.

Useful commands:

```powershell
./tool/run_bulletin_media_decoder_smoke.ps1 -SelfTest
./tool/run_bulletin_media_decoder_smoke.ps1 -FlutterPath <path-to-flutter> -NuGetPath <path-to-nuget.exe>
```

# Bulletin media gateway E2E runner

`run_bulletin_media_gateway_e2e.ps1` starts the local Python gateway and runs the Dart client through the selected-run artifact, preview bytes, one-time grant, and publish-result path. By default it uses a synthetic Bulletin board.

The runner accepts `-FlutterPath`, `-PythonPath`, and `-ValidationDir`. When the executable paths are omitted it uses `Get-Command` lookup. When `-ValidationDir` is omitted it uses the OS temp directory as the base. Every run writes into a unique child directory so receipts from separate runs are not overwritten.

On a zero-exit Flutter test, the script still fails unless the receipt exists, is complete, matches the fixture run and artifact identities, includes preview bytes, and reports `posted_readback_match`.

Pass `-BulletinBaseUrl` to test against an already running, isolated local Bulletin Worker. This mode accepts only loopback addresses and uses a temporary test identity. Start and stop the Worker separately; the runner does not manage its lifecycle.

```powershell
./tool/run_bulletin_media_gateway_e2e.ps1 -BulletinBaseUrl http://127.0.0.1:8787
```

Keep the run summary, Dart receipt, and Worker log together. The Dart receipt alone does not distinguish the synthetic board from the local Worker.
