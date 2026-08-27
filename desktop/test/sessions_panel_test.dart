// Falsifiers for the sessions view: it lists the journeys the gateway holds and
// opens the tapped one, so a session started on the PC is visible and reopenable
// from any device pointed at that gateway.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/sessions_panel.dart';

import 'journey_controller_test.dart'; // ScriptedJourneyApi, projection, journeyA

void main() {
  Widget host(SessionsPanel panel) =>
      MaterialApp(theme: flywheelLightTheme(), home: Scaffold(body: panel));

  testWidgets('lists the gateway sessions and opens the tapped one',
      (tester) async {
    final api = ScriptedJourneyApi()..reply('list', <JourneySummary>[projection()]);
    String? openedRef;
    JourneyLens? openedLens;
    await tester.pumpWidget(host(SessionsPanel(
        api: api,
        onOpen: (ref, lens) {
          openedRef = ref;
          openedLens = lens;
        })));
    await tester.pumpAndSettle();

    expect(find.text(journeyA), findsOneWidget); // the session row shows its ref
    await tester.tap(find.text(journeyA));
    await tester.pump();
    expect(openedRef, journeyA);
    expect(openedLens, JourneyLens.verify);
  });

  testWidgets('an empty gateway list shows an honest null', (tester) async {
    final api = ScriptedJourneyApi()..reply('list', const <JourneySummary>[]);
    await tester.pumpWidget(host(SessionsPanel(api: api, onOpen: (_, __) {})));
    await tester.pumpAndSettle();

    expect(find.textContaining('No sessions yet'), findsOneWidget);
  });
}
