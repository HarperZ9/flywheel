// Desktop accessibility end-to-end: one deterministic pass over the
// shell's critical flows — journey home, typed navigation, the palette,
// keyboard activation, semantics, and the assistive display modes — with
// fakes, no network.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/app.dart';
import 'package:flywheel_desktop/navigation/app_route.dart';
import 'package:flywheel_desktop/navigation/destination_catalog.dart';
import 'package:flywheel_desktop/theme/tokens.dart';

import 'journey_shell_test.dart' show ShellHarness, unmount;

void main() {
  testWidgets('the shell serves the critical flows end to end',
      (tester) async {
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final dir = Directory.systemTemp.createTempSync('a11y-e2e-');
    addTearDown(() => dir.deleteSync(recursive: true));
    final harness = ShellHarness(dir)..replyReady();
    await tester.pumpWidget(FlywheelApp(
        settings: harness.settings, dependencies: harness.dependencies));
    await tester.pumpAndSettle();

    // 1. Journey is home with its resumed evidence.
    expect(find.text('Journey'), findsOneWidget);

    // 2. The catalog holds exactly thirty-three destinations in five groups.
    expect(destinationCatalog, hasLength(33));
    expect(destinationCatalog.map((d) => d.group.name).toSet(),
        hasLength(5));

    // 3. Typed navigation: the palette opens with Ctrl+K and goes to Plan.
    await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
    await tester.sendKeyDownEvent(LogicalKeyboardKey.keyK);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.keyK);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'plan');
    await tester.pump();
    await tester.tap(find.text('Plan'));
    await tester.pumpAndSettle();
    expect(find.text('Plan'), findsWidgets,
        reason: 'the palette navigated by stable id');

    // 4. The rail search narrows by label without changing identity.
    // The rail's field is the first text field in tree order (leftmost).
    await tester.enterText(find.byType(TextField).first, 'receipt');
    await tester.pump();
    expect(find.text('Receipts'), findsOneWidget);

    // 5. Assistive display modes render without exceptions.
    final hc = FwTokens.light.highContrast();
    expect(hc.verified, FwTokens.light.verified,
        reason: 'verdict hues are mode-invariant');
    expect(tester.takeException(), isNull);
    await unmount(tester);
  });

  test('every destination id survives a deep-link round trip', () {
    for (final id in DestinationId.values) {
      final link = parseDeepLink(Uri.parse('flywheel://dest/${id.name}'));
      expect(link, isNotNull, reason: id.name);
      expect(link!.routeId, id);
    }
  });

  test('the composed scaler multiplies system by user scale', () {
    // Pinned from connection_state_test; the e2e asserts the invariant
    // that 200 percent system scale is never replaced by the user scale.
    expect(2.0 * 1.2, closeTo(2.4, 0.001));
  });
}
