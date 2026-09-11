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
        (
          'attention',
          scale,
          const RowanPose(attention: ui.Offset(0.8, -0.5)),
          0,
          false
        ),
        ('opening', scale, const RowanPose(opening: 0.8), 0, false),
        ('idle', scale, const RowanPose(), 2, true),
        ('static-time', scale, const RowanPose(), 2, false),
        ('landscape', scale, const RowanPose(), 0, false),
        ('portrait', scale, const RowanPose(), 0, false),
      ];
      final hashes = <String, String>{};
      for (final (name, size, pose, seconds, motion) in cases) {
        final width = name == 'landscape' ? (size * 1.5).round() : size;
        final height = name == 'portrait' ? (size * 1.5).round() : size;
        final shader = program.fragmentShader();
        final time = ValueNotifier<double>(seconds);
        final recorder = ui.PictureRecorder();
        RowanShaderPainter(
                shader: shader, time: time, pose: pose, motion: motion)
            .paint(ui.Canvas(recorder),
                ui.Size(width.toDouble(), height.toDouble()));
        final picture = recorder.endRecording();
        final watch = Stopwatch()..start();
        final image = await picture.toImage(width, height);
        final raw =
            (await image.toByteData(format: ui.ImageByteFormat.rawRgba))!;
        watch.stop();
        final bytes = raw.buffer.asUint8List();
        var covered = 0;
        var left = width, top = height, right = 0, bottom = 0;
        for (var i = 3; i < bytes.length; i += 4) {
          if (bytes[i] > 0) {
            covered++;
            final pixel = i ~/ 4;
            final x = pixel % width, y = pixel ~/ width;
            if (x < left) left = x;
            if (x > right) right = x;
            if (y < top) top = y;
            if (y > bottom) bottom = y;
          }
        }
        expect(covered, greaterThan(width * height * .05));
        expect(covered, lessThan(width * height * .95));
        expect((right - left - bottom + top).abs(), lessThanOrEqualTo(2),
            reason:
                'the artwork circle must remain round on non-square canvases');
        final digest = sha256.convert(bytes).toString();
        hashes[name] = digest;
        final frame = <String, Object>{
          'name': name,
          'width': width,
          'height': height,
          'pose_uniforms': pose.uniforms,
          'time_seconds': seconds,
          'motion': motion,
          'raw_rgba_sha256': digest,
          'covered_pixels': covered,
          'total_pixels': width * height,
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
        'attention',
        'opening',
        'idle'
      ]) {
        expect(hashes[pose], isNot(hashes['neutral-$scale']));
      }
      expect(hashes['static-time'], hashes['neutral-$scale'],
          reason: 'time cannot animate the default static companion');
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
