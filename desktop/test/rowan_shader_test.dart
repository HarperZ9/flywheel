import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/rowan_avatar.dart';
import 'package:flywheel_desktop/widgets/rowan_shader.dart';

void main() {
  test('pose uniforms keep malformed values finite and bounded', () {
    const pose =
        RowanPose(gaze: Offset(double.nan, 5), yaw: -9, mouth: double.infinity);
    expect(pose.uniforms, [0, 1, -0.6, 0]);
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
