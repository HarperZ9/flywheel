import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;
import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/rowan_avatar.dart';
import 'package:flywheel_desktop/widgets/rowan_shader.dart';

void main() {
  testWidgets('abstract companion and fallback compose on both app grounds',
      (tester) async {
    final program = await tester.runAsync(RowanShader.load);
    final output = Platform.environment['ROWAN_CAPTURE_DIR'];
    final source = File('shaders/rowan.frag');
    final sourceHash = sha256.convert(source.readAsBytesSync()).toString();
    final frames = <Map<String, Object>>[];
    for (final dark in [false, true]) {
      final theme = dark ? flywheelDarkTheme() : flywheelLightTheme();
      final ground = dark ? FwTokens.dark.ground : FwTokens.light.ground;
      for (final (size, fallback) in [
        (32.0, false),
        (64.0, false),
        (320.0, false),
        (64.0, true)
      ]) {
        final boundaryKey = GlobalKey();
        await tester.pumpWidget(MaterialApp(
          theme: theme,
          home: Scaffold(
              body: Center(
                  child: RepaintBoundary(
            key: boundaryKey,
            child: ColoredBox(
                color: ground,
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: RowanAvatar(
                      size: size,
                      loadProgram: () async {
                        if (fallback) {
                          throw UnsupportedError('renderer unavailable');
                        }
                        return program!;
                      }),
                )),
          ))),
        ));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        expect(find.byType(Image), findsNothing);
        final boundary = boundaryKey.currentContext!.findRenderObject()
            as RenderRepaintBoundary;
        await tester.runAsync(() async {
          final image = await boundary.toImage();
          final raw =
              (await image.toByteData(format: ui.ImageByteFormat.rawRgba))!
                  .buffer
                  .asUint8List();
          final argb = ground.toARGB32();
          expect(raw.take(4),
              [(argb >> 16) & 255, (argb >> 8) & 255, argb & 255, 255],
              reason: 'transparent artwork corners retain the app ground');
          if (!fallback) {
            final index = ((12 + (size * .9).floor()) * image.width +
                    12 +
                    (size / 2).floor()) *
                4;
            expect(raw.sublist(index, index + 3).reduce((a, b) => a + b),
                lessThan(100),
                reason:
                    'the intentional black art disk stays dark in either theme');
          }
          final name =
              '${dark ? 'dark' : 'light'}-${fallback ? 'fallback' : 'companion'}-${size.toInt()}';
          final frame = <String, Object>{
            'name': name,
            'width': image.width,
            'height': image.height,
            'raw_rgba_sha256': sha256.convert(raw).toString()
          };
          if (output != null) {
            final png =
                (await image.toByteData(format: ui.ImageByteFormat.png))!
                    .buffer
                    .asUint8List();
            final file = File('$output/surfaces/$name.png');
            file.parent.createSync(recursive: true);
            file.writeAsBytesSync(png);
            frame['png_sha256'] = sha256.convert(png).toString();
          }
          frames.add(frame);
          image.dispose();
        });
      }
    }
    expect(sha256.convert(source.readAsBytesSync()).toString(), sourceHash);
    if (output != null) {
      File('$output/surfaces/capture.json')
          .writeAsStringSync(const JsonEncoder.withIndent('  ').convert({
        'shader_sha256': sourceHash,
        'backend': 'Flutter widget test engine / RenderRepaintBoundary.toImage',
        'does_not_prove':
            'device performance, artistic preference, or mobile readiness',
        'frames': frames,
      }));
    }
  });
}
