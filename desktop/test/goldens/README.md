# Chat navigation and screen-feed baselines

These five fixtures use bundled Hanken Grotesk, Cascadia Mono and Material Icons
with Flutter 3.44.6. Host font rasterization still differs. Windows baselines
remain in this directory; Linux baselines live in `linux/`. The helper
`../platform_golden.dart` selects the host baseline. A missing baseline fails;
there is no platform skip or pixel tolerance.

Linux captures were reviewed from desktop-ci run
[35039951256](https://github.com/HarperZ9/flywheel/actions/runs/35039951256),
PR head `82a05ee1a0ef3fa2ef78da427ba5e10390dd7a34`, tested merge
`57557b49c9de02a21dd10d19f0f0e93caf3aadaa`. All five actual/master/diff pairs
were inspected before accepting the Linux images. Differences were around text,
icons and a few content-sized control edges. Panels, text wrapping and the
synthetic scene retained their geometry and content. Original Windows bytes
were preserved.

Run on each supported host from `desktop/`:

```sh
flutter test test/chat_navigation_render_test.dart test/live_screen_render_test.dart
```

For an intentional visual change, run those tests with `--update-goldens` on
each host, then review the images and layout assertions before committing.
Do not copy a failing image into a baseline without inspecting its difference.
An additional host needs its own reviewed directory and CI coverage.

These are synthetic widget fixtures. They do not establish real screen capture,
model delivery, audio playback, installed rendering or general accessibility.
See [Flutter's font guidance](https://api.flutter.dev/flutter/flutter_test/matchesGoldenFile.html).
