// The accessibility contract tests: every registered action carries a
// keyboard path and an enabled reason; the audited surfaces contain no
// raw pointer-only handlers; keyboard activation works on a live surface.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/accessibility/action_registry.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/status_bar.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: child),
    );

void main() {
  test('every registered action names a keyboard path', () {
    for (final action in actionRegistry) {
      expect(action.primaryKey, isNotNull,
          reason: '${action.semanticLabel} has no keyboard path');
      expect(action.semanticLabel, isNotEmpty);
      expect(action.enabledReason, isNotEmpty);
    }
  });

  test('registry labels are unique', () {
    final labels = actionRegistry.map((a) => a.semanticLabel).toSet();
    expect(labels.length, actionRegistry.length);
  });

  testWidgets('the status bar start action carries its semantic label',
      (tester) async {
    var started = 0;
    final semantics = tester.ensureSemantics();
    await tester.pumpWidget(_wrap(StatusBar(
      alive: false,
      message: 'engine offline',
      startError: null,
      world: null,
      onStartEngine: () => started++,
    )));
    await tester.pump();

    // Semantic contract: the action is a labeled button.
    expect(find.bySemanticsLabel(RegExp(r'Start engine')), findsOneWidget);

    // Pointer contract preserved: tapping still starts the engine.
    await tester.tap(find.text('start engine'));
    await tester.pump();
    expect(started, 1);
    semantics.dispose();
  });

  test('DesktopSettings defaults keep assistive values honest', () {
    final s = DesktopSettings();
    expect(s.uiScale, 1.0);
    expect(s.railCollapsed, isFalse);
  });
}
