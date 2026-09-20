import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/studio_body_step.dart';
import 'package:flywheel_desktop/models/studio_body_protocol.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/studio_body_output.dart';

void main() {
  Future<void> show(WidgetTester tester, StudioBodyStepResult result) =>
      tester.pumpWidget(MaterialApp(
          theme: flywheelLightTheme(),
          home: Scaffold(body: StudioBodyOutput(result: result))));

  testWidgets('accepted render shows actual bytes with frame navigation',
      (tester) async {
    await show(tester, _result());
    await tester.pumpAndSettle();
    expect(find.byType(Image), findsOneWidget);
    expect(find.text('Frame 1 of 2'), findsOneWidget);
    await tester.tap(find.byTooltip('Next frame'));
    await tester.pump();
    expect(find.text('Frame 2 of 2'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('corruption in a later frame rejects the whole preview',
      (tester) async {
    await show(tester, _result(corruptSecond: true));
    expect(find.byType(Image), findsNothing);
    expect(find.textContaining('Output unavailable'), findsOneWidget);
  });

  testWidgets('denied action cannot display attached media as a result',
      (tester) async {
    await show(tester, _result(accepted: false));
    expect(find.byType(Image), findsNothing);
    expect(find.textContaining('No verified output'), findsOneWidget);
  });

  testWidgets('a success field cannot override a denying authority receipt',
      (tester) async {
    await show(tester, _result(decision: 'deny'));
    expect(find.byType(Image), findsNothing);
    expect(find.textContaining('No verified output'), findsOneWidget);
  });

  testWidgets('corrupt receipt fails closed and replacement clears old frame',
      (tester) async {
    await show(tester, _result());
    await tester.pumpAndSettle();
    await show(tester, _result(corrupt: true));
    await tester.pumpAndSettle();
    expect(find.byType(Image), findsNothing);
    expect(find.textContaining('Output unavailable'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

StudioBodyStepResult _result(
    {bool accepted = true,
    bool corrupt = false,
    bool corruptSecond = false,
    String decision = 'allow'}) {
  final bytes = base64Decode(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=');
  final frame = {
    'png_base64': base64Encode(bytes),
    'frame_sha256': corrupt ? '0' * 64 : sha256.convert(bytes).toString(),
  };
  return StudioBodyStepResult.fromJson({
    'schema': studioBodyStepResponseSchema,
    'accepted': accepted,
    'action_kind': studioBodyEngineActionKind,
    'receipt': {
      'frame_count': 2,
      'frames': [
        frame,
        {...frame, if (corruptSecond) 'frame_sha256': '0' * 64}
      ]
    },
    'authority_receipt': {
      'decision': decision,
      'acted': true,
      'verified': true
    },
  });
}
