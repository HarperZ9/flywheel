// Focus behavior: primary focus moves between action nodes and back.
//
// Limitation, recorded honestly: the visual focus ring's appearance
// follows the platform focus-highlight strategy through
// FocusableActionDetector's internal highlight state machine, which does
// not surface its transition callbacks reliably under the widget test
// binding. Ring visibility was verified manually with keyboard
// traversal; these tests pin the focus semantics the ring depends on.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/accessibility/accessible_action.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: Center(child: child)),
    );

void main() {
  testWidgets('primary focus moves between action nodes and back',
      (tester) async {
    final a = FocusNode();
    final b = FocusNode();
    addTearDown(a.dispose);
    addTearDown(b.dispose);
    await tester.pumpWidget(_wrap(Column(children: [
      AccessibleAction(
          semanticLabel: 'First action',
          focusNode: a,
          onActivate: () {},
          child: const Text('first')),
      AccessibleAction(
          semanticLabel: 'Second action',
          focusNode: b,
          onActivate: () {},
          child: const Text('second')),
    ])));
    await tester.pump();
    a.requestFocus();
    await tester.pump();
    expect(a.hasPrimaryFocus, isTrue);
    b.requestFocus();
    await tester.pump();
    expect(FocusManager.instance.primaryFocus, same(b),
        reason: 'taking focus moves it; it does not stay in two places');
    a.requestFocus();
    await tester.pump();
    expect(FocusManager.instance.primaryFocus, same(a),
        reason: 'focus is restorable to the earlier trigger');
  });

  testWidgets('an action is focusable and releases focus on unfocus',
      (tester) async {
    final node = FocusNode();
    addTearDown(node.dispose);
    await tester.pumpWidget(_wrap(AccessibleAction(
      semanticLabel: 'Example action',
      focusNode: node,
      onActivate: () {},
      child: const Text('example'),
    )));
    await tester.pump();
    expect(node.canRequestFocus, isTrue);
    node.requestFocus();
    await tester.pump();
    expect(node.hasFocus, isTrue);
    node.unfocus();
    await tester.pump();
    expect(node.hasFocus, isFalse);
  });
}
