// The Roadmap destination: goals with per-child verification status,
// the verification floor, honest limits on the page, and the offline
// state that names its command. The engine assembles everything; this
// surface renders and re-reads.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_roadmap.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/roadmap_view.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _roadmapBody = {
  'roadmap': {
    'schema': 'flywheel.pm-roadmap/v1',
    'generated_at': '2026-08-25T09:00:00Z',
    'goals': [
      {
        'ref': 'swarm_aaaaaaaaaaaaaaaa',
        'state': 'sealed',
        'verdict': 'satisfied',
        'verified_children': '2 of 2',
        'total': 2,
      },
      {
        'ref': 'swarm_det987654321',
        'state': 'detached',
        'verdict': null,
        'verified_children': null,
        'total': 3,
      },
      {
        'ref': 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        'kind': 'journey',
        'goal': 'land the finance pack',
        'state': 'journey:preflight',
        'stage': 'preflight',
        'verdict': null,
        'verified_children': '1 of 2',
        'total': 2,
      },
    ],
    'verification': {'skills_bound': 2, 'sealed_goals': 1,
                     'open_goals': 1},
    'does_not_prove': [
      'a satisfied quorum attests children ran and reported; it does '
          'not prove the goal was achieved',
    ],
  },
  'one_page': '# Roadmap -- 2026-08-25T09:00:00Z',
};

void main() {
  testWidgets('RoadmapView renders goals, floor, and its own limits',
      (tester) async {
    final api = RoadmapApi(
      httpClient: MockClient((request) async {
        expect(request.url.path, '/api/pm/roadmap');
        return http.Response(jsonEncode(_roadmapBody), 200,
            headers: {'content-type': 'application/json'});
      }),
    );
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: RoadmapView(api: api, alive: true))));
    await tester.pumpAndSettle();

    expect(find.text('swarm_aaaaaaaaaaaaaaaa'), findsOneWidget);
    expect(find.text('SATISFIED'), findsOneWidget);
    expect(find.text('2 of 2'), findsOneWidget);
    // a journey row titles itself with its goal; the stage is the state
    expect(find.text('land the finance pack'), findsOneWidget);
    expect(find.text('preflight'), findsOneWidget);
    expect(find.text('1 of 2'), findsOneWidget);
    // open rows stay visible with their state, not a fake verdict
    expect(find.text('detached'), findsWidgets);

    // drag to the verification floor and the page's own limits; StatTile
    // renders labels as mono uppercase kickers
    for (var i = 0; i < 10; i++) {
      if (find.text('SKILLS BOUND').evaluate().isNotEmpty) break;
      await tester.drag(find.byType(ListView).first,
          const Offset(0, -250));
      await tester.pumpAndSettle();
    }
    expect(find.text('SKILLS BOUND'), findsOneWidget);
    expect(find.text('2'), findsWidgets);
    expect(find.textContaining('does not prove'), findsOneWidget);
  });

  testWidgets('RoadmapView names the command when offline',
      (tester) async {
    final api = RoadmapApi(httpClient: MockClient((request) async {
      throw StateError('offline surface must not call the engine');
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: RoadmapView(api: api, alive: false))));
    expect(find.textContaining('engine is offline'), findsOneWidget);
    expect(find.text('flywheel up'), findsOneWidget);
  });
}
