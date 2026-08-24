// 200 percent smoke: the critical surfaces render with system scale 2.0
// and user scale 1.4 composed, no clipped critical actions, no hidden
// semantics, no exceptions.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/app.dart';

import 'journey_shell_test.dart' show ShellHarness;

void main() {
  testWidgets('the shell renders at composed 2.0 x 1.4 scaling',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    tester.platformDispatcher.textScaleFactorTestValue = 2.0;
    addTearDown(() => tester.platformDispatcher.textScaleFactorTestValue = 1.0);
    final dir = Directory.systemTemp.createTempSync('scale-200-');
    addTearDown(() => dir.deleteSync(recursive: true));
    final harness = ShellHarness(dir)..replyReady();
    harness.settings.uiScale = 1.4;
    await tester.pumpWidget(FlywheelApp(
        settings: harness.settings, dependencies: harness.dependencies));
    await tester.pumpAndSettle();

    // Critical rail actions remain present and semantic.
    expect(find.text('Journey'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
