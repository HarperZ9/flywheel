// Media capture + smoke test for the first-run Rowan walkthrough.
//
// The walkthrough is the demo and the marketing capture as well as the tour,
// so its appearance is a shipped surface, not just an internal screen. This
// file has two jobs, kept apart on purpose:
//
//  1. Media capture. Run with --update-goldens to write one PNG per step to
//     test/goldens/. Those frames are the marketing capture:
//
//       flutter test --update-goldens test/rowan_launch_tour_golden_test.dart
//
//  2. Smoke test. On a normal run it walks all nine steps and asserts the
//     structure the frames depend on: the avatar leads step one, every step
//     header renders, and nothing throws. These run on every OS.
//
// The pixel compare is gated behind autoUpdateGoldenFiles, so it fires ONLY
// during a capture run and NEVER during CI. The frames are deliberately not a
// committed CI golden, for two reasons: text rasterizes differently across
// OSes, so a Windows frame would not match the ubuntu leg, and the avatar
// here is the drawn fallback, whose exact pixels are not a contract. The PNGs
// are media artifacts, git-ignored so a parallel checkout cannot sweep them
// in. The behavioral assertions are the regression guard for this screen;
// theme_typography_test guards the fonts cross-OS.
//
// The shader avatar falls back to its named drawn placeholder under
// flutter_test (no runtime shader program), which is the honest floor: the
// frame shows exactly what a machine that cannot compile the shader sees.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/rowan_launch_tour.dart';
import 'package:flywheel_desktop/widgets/rowan_presenter.dart';

Future<ByteData> _fontFile(String path) async =>
    ByteData.sublistView(await File(path).readAsBytes());

Future<void> _loadAppFonts() async {
  // Load every weight the tour draws so no glyph falls back: body is 400,
  // titles are 600/700, the display is 800, and buttons are 600. A missing
  // weight would rasterize as the flutter_test placeholder box, not the real
  // face, and the captured frame would misrepresent the shipped screen.
  final text = FontLoader(kTextFamily)
    ..addFont(_fontFile('assets/fonts/hanken-grotesk-light.ttf'))
    ..addFont(_fontFile('assets/fonts/hanken-grotesk-regular.ttf'))
    ..addFont(_fontFile('assets/fonts/hanken-grotesk-medium.ttf'))
    ..addFont(_fontFile('assets/fonts/hanken-grotesk-semibold.ttf'))
    ..addFont(_fontFile('assets/fonts/hanken-grotesk-bold.ttf'))
    ..addFont(_fontFile('assets/fonts/hanken-grotesk-extrabold.ttf'));
  final mono = FontLoader(kMonoFamily)
    ..addFont(_fontFile('assets/fonts/CascadiaMono.ttf'));
  await Future.wait([text.load(), mono.load()]);
}

/// Renders the tour card centered on the app ground, the way a first launch
/// shows it, so the captured frame reads as a real screen and not a bare card.
Widget _frame() => MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: flywheelLightTheme(),
      home: const Scaffold(
        body: Center(child: RowanWalkthroughTour(onOpenStudio: _noop)),
      ),
    );

void _noop() {}

/// The nine frames in step order, named by what each step shows.
const _frames = <String>[
  'goldens/tour_1_meet_rowan.png',
  'goldens/tour_2_the_app.png',
  'goldens/tour_3_together.png',
  'goldens/tour_4_receipts.png',
  'goldens/tour_5_today.png',
  'goldens/tour_6_still_open.png',
  'goldens/tour_7_the_idea.png',
  'goldens/tour_8_whats_next.png',
  'goldens/tour_9_your_turn.png',
];

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(_loadAppFonts);

  testWidgets('captures every walkthrough step as a shipped frame',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(640, 760));
    addTearDown(() async => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(_frame());
    await tester.pumpAndSettle();

    // Step 1 leads with the shader avatar; the rest are copy cards.
    expect(find.byType(RowanPresenter), findsOneWidget);
    expect(find.text("I'm Rowan."), findsOneWidget);

    for (var i = 0; i < _frames.length; i++) {
      expect(find.text('Step ${i + 1} of ${_frames.length}'), findsOneWidget,
          reason: 'the tour must render step ${i + 1} before it is captured');
      // Pixel compare only during a capture run (--update-goldens). CI never
      // reaches this branch, so an OS rasterization difference cannot flake it.
      if (autoUpdateGoldenFiles) {
        await expectLater(
            find.byType(RowanWalkthroughTour), matchesGoldenFile(_frames[i]));
      }
      if (i < _frames.length - 1) {
        await tester.tap(find.text('Next'));
        await tester.pumpAndSettle();
      }
    }

    expect(tester.takeException(), isNull);
  });
}
