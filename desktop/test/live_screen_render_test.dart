import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/live_screen_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/live_screen_panel.dart';
import 'screen_capture_fonts.dart';
import 'platform_golden.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(loadScreenCaptureFonts);
  for (final scenario in [
    ('wide', const Size(1000, 850), 1.0),
    ('narrow_large_text', const Size(460, 1000), 1.4),
  ]) {
    testWidgets('screen feed renders ${scenario.$1}', (tester) async {
      await tester.binding.setSurfaceSize(scenario.$2);
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final bytes = (await tester.runAsync(_syntheticFrame))!;
      final digest = sha256.convert(bytes).toString();
      final identity = <String, Object?>{
        'session_id': 'synthetic-session',
        'source_id': 'synthetic:studio',
        'source_sequence': 42,
        'aggregate_sequence': 42,
        'frame_sha256': digest,
      };
      final frame = LiveScreenFrame.fromJson({
        ...identity,
        'captured_at_utc': '2026-09-15T11:00:03Z',
        'width': 640,
        'height': 300,
      });
      final delivery = LiveScreenDelivery.fromJson({
        ...identity,
        'frame': identity,
        'model_route': 'test-adapter',
        'model': 'synthetic-model',
        'delivery_mode': 'sampled_image',
        'delivered_at_utc': '2026-09-15T11:00:04Z',
        'frame_age_ms': 1000,
        'stale': false,
      });
      await tester.pumpWidget(MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: flywheelLightTheme(),
        home: MediaQuery(
          data: MediaQueryData(
              size: scenario.$2, textScaler: TextScaler.linear(scenario.$3)),
          child: Scaffold(
              body: RepaintBoundary(
            key: const ValueKey('screen-capture'),
            child: ColoredBox(
              color: FwTokens.light.ground,
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(16),
                child: LiveScreenPanel(
                  sources: [
                    LiveScreenSource.fromJson(const {
                      'source_id': 'synthetic:studio',
                      'kind': 'synthetic',
                      'label': 'Studio fixture',
                      'backend': 'synthetic',
                      'available': true,
                    })
                  ],
                  selected: const {'synthetic:studio'},
                  state: ScreenCaptureState.running,
                  onSelectionChanged: (_) {},
                  onPause: () {},
                  onStop: () {},
                  previewBytes: bytes,
                  previewFrame: frame,
                  deliveredFrame: frame,
                  delivery: delivery,
                  now: () => DateTime.utc(2026, 9, 15, 11, 0, 5),
                ),
              ),
            ),
          )),
        ),
      ));
      await tester.runAsync(() => precacheImage(
          MemoryImage(bytes), tester.element(find.byType(LiveScreenPanel))));
      await tester.pump();
      expect(tester.widget<RawImage>(find.byType(RawImage)).image, isNotNull);
      expect(tester.takeException(), isNull);
      expect(find.text('Pause').hitTestable(), findsOneWidget);
      expect(find.text('Stop sharing').hitTestable(), findsOneWidget);
      await expectLater(find.byKey(const ValueKey('screen-capture')),
          matchesGoldenFile(platformGolden('live_screen_${scenario.$1}')));
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
}

/// Synthetic geometry only. This fixture contains no real monitor/user content.
Future<Uint8List> _syntheticFrame() async {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  canvas.drawColor(const Color(0xffedf0f2), BlendMode.src);
  canvas.drawRect(const Rect.fromLTWH(24, 80, 170, 190),
      Paint()..color = const Color(0xffd7b77a));
  canvas.drawCircle(
      const Offset(320, 170), 80, Paint()..color = const Color(0xff7294a4));
  canvas.drawRRect(
      RRect.fromRectAndRadius(
          const Rect.fromLTWH(450, 100, 160, 130), const Radius.circular(20)),
      Paint()..color = const Color(0xffaaa09a));
  final label = TextPainter(
      text: const TextSpan(
          text: 'SYNTHETIC CAPTURE FIXTURE',
          style: TextStyle(
              fontFamily: 'Cascadia Mono',
              fontSize: 22,
              color: Color(0xff17191b))),
      textDirection: TextDirection.ltr)
    ..layout();
  label.paint(canvas, const Offset(24, 24));
  final picture = recorder.endRecording();
  final image = await picture.toImage(640, 300);
  final data = (await image.toByteData(format: ui.ImageByteFormat.png))!;
  final bytes = data.buffer.asUint8List();
  image.dispose();
  picture.dispose();
  return bytes;
}
