// Two MEDIUM findings: an empty/zero set must not render as a green
// VERIFIED verdict, and gateway models must degrade on malformed lists
// rather than crash (their own "never crash" contract).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/workflow_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/instruments_view.dart';
import 'package:flywheel_desktop/widgets/fw.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void main() {
  testWidgets('an empty instruments register does not render VERIFIED',
      (tester) async {
    await tester.pumpWidget(_wrap(InstrumentList(const {
      'instruments': [],
      'present_count': 0,
      'total': 0,
    })));
    // find the header verdict pill; it must not read verified on an empty set
    final pills = tester.widgetList<VerdictPill>(find.byType(VerdictPill));
    expect(pills.every((p) => p.status != 'verified'), isTrue,
        reason: 'empty/zero must not be a green win');
  });

  test('WorkflowDef parses a steps list with null and bare-string entries', () {
    final d = WorkflowDef.fromJson({
      'name': 'wf',
      'description': 'x',
      'steps': [
        {'name': 'a'},
        null,
        'not-a-map',
        {'name': 'b'},
      ],
    });
    expect(d.stepNames, ['a', 'b']);
  });

  test('WorkflowDef tolerates a non-list steps field', () {
    final d = WorkflowDef.fromJson({'name': 'wf', 'steps': 'oops'});
    expect(d.stepNames, isEmpty);
  });
}
