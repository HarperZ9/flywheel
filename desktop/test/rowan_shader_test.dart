import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/rowan_avatar.dart';
import 'package:flywheel_desktop/widgets/rowan_shader.dart';

/// The reviewed source hash recorded in docs/ROWAN-SHADER.md. The doc
/// describes the shader's cost budget (64 march steps, six normal probes) and
/// palette in terms of this exact source. Pinning it here turns that prose into
/// a gate: an edit to rowan.frag that changes behavior without updating the doc
/// and this constant in the same commit fails, instead of leaving the doc
/// silently describing a shader that no longer exists. The render test only
/// checks the source against itself within a run, so it cannot catch that drift.
const expectedRowanShaderSha256 =
    '72cd6136bba787ef79080dc9bfdc39b533517e522342cb5fb8ce22247f8486cb';

void main() {
  test('pose uniforms keep malformed values finite and bounded', () {
    const pose = RowanPose(
        attention: Offset(double.nan, 5), yaw: -9, opening: double.infinity);
    expect(pose.uniforms, [0, 1, -0.6, 0]);
  });

  test('rowan.frag matches the reviewed hash recorded in ROWAN-SHADER.md', () {
    // The file is committed pure LF (.gitattributes: desktop/shaders/*.frag
    // text eol=lf), so this hash is stable across platforms and checkouts.
    final source = File('shaders/rowan.frag');
    expect(source.existsSync(), isTrue,
        reason: 'run from the desktop/ directory, where the path resolves');
    final actual = sha256.convert(source.readAsBytesSync()).toString();
    expect(actual, expectedRowanShaderSha256,
        reason: 'rowan.frag changed but the reviewed hash in '
            'docs/ROWAN-SHADER.md and expectedRowanShaderSha256 were '
            'not updated in the same commit; the doc now describes a shader '
            'that is no longer on disk');
  });

  testWidgets('unsupported shader keeps a named drawn fallback, no image',
      (tester) async {
    final semantics = tester.ensureSemantics();
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
          body: RowanAvatar(
              loadProgram: () async =>
                  throw UnsupportedError('private driver detail'))),
    ));
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel('Rowan, simple fallback drawing'),
        findsOneWidget);
    expect(find.byType(Image), findsNothing);
    expect(find.textContaining('private driver'), findsNothing);
    expect(tester.takeException(), isNull);
    semantics.dispose();
  });
}
