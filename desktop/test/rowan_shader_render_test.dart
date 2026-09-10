import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/widgets/rowan_shader.dart';

void main() {
  testWidgets('real compiled shader draws geometry and responds to pose',
      (tester) async {
    await tester.runAsync(() async {
      final output = Platform.environment['ROWAN_CAPTURE_DIR'];
      final source = File('shaders/rowan.frag');
      final sourceHash = sha256.convert(source.readAsBytesSync()).toString();
      final program = await RowanShader.load();
      final frames = <Map<String, Object>>[];
      final scale = output == null ? 128 : 320;
      final cases = <(String, int, RowanPose, double, bool)>[
        for (final size in [32, 64, scale, if (output != null) 640]) ...[
          ('neutral-$size', size, const RowanPose(), 0, false),
          ('yaw-left-$size', size, const RowanPose(yaw: -0.4), 0, false),
          ('yaw-right-$size', size, const RowanPose(yaw: 0.4), 0, false),
        ],
        ('gaze', scale, const RowanPose(gaze: ui.Offset(0.8, -0.5)), 0, false),
        ('mouth', scale, const RowanPose(mouth: 0.8), 0, false),
        ('blink', scale, const RowanPose(), .10, true),
      ];
      final hashes = <String, String>{};
      for (final (name, size, pose, seconds, motion) in cases) {
        final shader = program.fragmentShader();
        final time = ValueNotifier<double>(seconds);
        final recorder = ui.PictureRecorder();
        RowanShaderPainter(
                shader: shader, time: time, pose: pose, motion: motion)
            .paint(ui.Canvas(recorder), ui.Size.square(size.toDouble()));
        final picture = recorder.endRecording();
        final watch = Stopwatch()..start();
        final image = await picture.toImage(size, size);
        final raw =
            (await image.toByteData(format: ui.ImageByteFormat.rawRgba))!;
        watch.stop();
        final bytes = raw.buffer.asUint8List();
        var covered = 0;
        for (var i = 3; i < bytes.length; i += 4) {
          if (bytes[i] > 0) covered++;
        }
        expect(covered, greaterThan(size * size * .05));
        expect(covered, lessThan(size * size * .95));
        final digest = sha256.convert(bytes).toString();
        hashes[name] = digest;
        final frame = <String, Object>{
          'name': name,
          'width': size,
          'height': size,
          'pose_uniforms': pose.uniforms,
          'time_seconds': seconds,
          'motion': motion,
          'raw_rgba_sha256': digest,
          'covered_pixels': covered,
          'total_pixels': size * size,
          'raster_and_readback_microseconds': watch.elapsedMicroseconds,
        };
        if (output != null) {
          final png = (await image.toByteData(format: ui.ImageByteFormat.png))!;
          final file = File('$output/$name.png');
          file.parent.createSync(recursive: true);
          file.writeAsBytesSync(png.buffer.asUint8List());
          frame['png_sha256'] =
              sha256.convert(png.buffer.asUint8List()).toString();
        }
        frames.add(frame);
        image.dispose();
        picture.dispose();
        shader.dispose();
        time.dispose();
      }
      for (final pose in [
        'yaw-left-$scale',
        'yaw-right-$scale',
        'gaze',
        'mouth',
        'blink'
      ]) {
        expect(hashes[pose], isNot(hashes['neutral-$scale']));
      }
      for (final size in [32, 64, scale, if (output != null) 640]) {
        expect(hashes['yaw-left-$size'], isNot(hashes['neutral-$size']));
        expect(hashes['yaw-right-$size'], isNot(hashes['neutral-$size']));
        expect(hashes['yaw-left-$size'], isNot(hashes['yaw-right-$size']));
      }
      expect(sha256.convert(source.readAsBytesSync()).toString(), sourceHash,
          reason: 'capture must bind to an unchanged shader source');
      if (output != null) {
        File('$output/flutter-capture.json')
            .writeAsStringSync(const JsonEncoder.withIndent('  ').convert({
          'shader_sha256': sourceHash,
          'backend': 'Flutter test engine FragmentProgram / Picture.toImage',
          'does_not_prove':
              'GPU device throughput, sustained FPS, mobile performance, or semantic identity quality',
          'frames': frames,
        }));
      }
    });
  });
}
