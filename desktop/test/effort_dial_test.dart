// effort_dial_test.dart — the dial the operator can reach, and the receipt
// that does not overstate it.
//
// The engine has stamped a resolved effort into every run receipt since July
// while the app hardcoded a step budget and never sent one. These hold the
// two properties that gap violated: the control sets the wire value the
// engine reads, and a capped run is reported as capped.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/effort_dial.dart';
import 'package:flywheel_desktop/widgets/run_evidence_card.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: child),
    );

void main() {
  testWidgets('every engine dial is reachable as a segment', (tester) async {
    await tester.pumpWidget(_wrap(
      EffortDial(value: EffortLevel.standard, onChanged: (_) {}),
    ));
    for (final level in EffortLevel.values) {
      expect(find.text(level.wire), findsOneWidget,
          reason: '${level.wire} must be selectable');
    }
  });

  testWidgets('choosing a level reports the wire value the engine reads',
      (tester) async {
    EffortLevel? chosen;
    await tester.pumpWidget(_wrap(
      EffortDial(value: EffortLevel.standard, onChanged: (v) => chosen = v),
    ));
    await tester.tap(find.text('ultra'));
    await tester.pump();
    expect(chosen, EffortLevel.ultra);
    expect(chosen!.wire, 'ultra');
  });

  testWidgets('the step budget is shown with the choice', (tester) async {
    await tester.pumpWidget(_wrap(
      EffortDial(value: EffortLevel.high, onChanged: (_) {}),
    ));
    expect(find.text('12 steps'), findsOneWidget);
  });

  testWidgets('a disabled dial does not change mid-run', (tester) async {
    EffortLevel? chosen;
    await tester.pumpWidget(_wrap(
      EffortDial(
          value: EffortLevel.low, onChanged: (v) => chosen = v, enabled: false),
    ));
    await tester.tap(find.text('high'));
    await tester.pump();
    expect(chosen, isNull, reason: 'a run in flight keeps the dial it started with');
  });

  test('an unknown wire value falls back rather than throwing', () {
    expect(EffortLevel.fromWire('turbo'), EffortLevel.standard);
    expect(EffortLevel.fromWire(null), EffortLevel.standard);
    expect(EffortLevel.fromWire('ultra'), EffortLevel.ultra);
  });

  testWidgets('a capped run is reported as capped, not at its nominal budget',
      (tester) async {
    await tester.pumpWidget(_wrap(ViewOnly(run: const {
      'effort': {
        'name': 'high',
        'max_steps': 12,
        'max_steps_applied': 6,
        'max_steps_overridden': true,
      },
    })));
    expect(find.textContaining('6 of 12 steps'), findsOneWidget);
    expect(find.textContaining('capped'), findsOneWidget);
  });

  testWidgets('an unoverridden run reports the budget it actually had',
      (tester) async {
    await tester.pumpWidget(_wrap(ViewOnly(run: const {
      'effort': {
        'name': 'low',
        'max_steps': 4,
        'max_steps_applied': 4,
        'max_steps_overridden': false,
      },
    })));
    expect(find.textContaining('low · 4 steps'), findsOneWidget);
    expect(find.textContaining('capped'), findsNothing);
  });
}

/// The evidence card needs a scrollable host in tests; this keeps the card
/// itself untouched by test-only layout.
class ViewOnly extends StatelessWidget {
  final Map<String, dynamic> run;
  const ViewOnly({super.key, required this.run});

  @override
  Widget build(BuildContext context) =>
      SingleChildScrollView(child: RunEvidenceCard(run: run));
}
