// The Runners destination: the pool, and the two numbers that stop it
// reading as a wall of green dots. A pool losing machines and a pool
// merely busy print the same enrolled count, so the lapsed leases and
// the chain verdict are asserted here beside the roster.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_runners.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/runners_view.dart';
import 'package:flywheel_desktop/widgets/fw.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _rosterBody = {
  'schema': 'flywheel.runner-roster/v1',
  'read_at': '2026-09-06T09:00:00Z',
  'now': '2026-09-06T09:00:00Z',
  'chain_intact': true,
  'events': 9,
  'runners': [
    {
      'runner_id': 'rnr-alpha',
      'labels': ['linux', 'gpu'],
      'enrolled': true,
      'enrolled_at': '2026-09-06T08:40:00Z',
    },
    {
      'runner_id': 'rnr-beta',
      'labels': ['windows'],
      'enrolled': false,
      'enrolled_at': '2026-09-06T08:41:00Z',
    },
  ],
  'jobs': [
    {
      'job_id': 'job-held',
      'requires': ['gpu'],
      'state': 'leased',
      'runner_id': 'rnr-alpha',
      'lease_expires': '2026-09-06T09:05:00Z',
      'ok': null,
    },
    {
      'job_id': 'job-waiting',
      'requires': ['windows'],
      'state': 'queued',
      'runner_id': null,
      'lease_expires': null,
      'ok': null,
    },
    {
      'job_id': 'job-finished-badly',
      'requires': <String>[],
      'state': 'done',
      'runner_id': 'rnr-alpha',
      'lease_expires': null,
      'ok': false,
    },
  ],
  'queued': 4,
  'leased': 5,
  'leases_lapsed': 2,
  'tickets_unspent': 3,
};

const _refusalBody = {
  'schema': 'flywheel.runner-ack/v1',
  'accepted': false,
  'refused': 'the runner chain is broken',
};

/// A viewport tall enough to build every row, so a failed assertion means
/// the surface omitted something rather than the list not having
/// scrolled to it.
void _tallViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1400, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

/// Read one headline tile by the label it was authored with, so a numeral
/// asserted here belongs to the count it names rather than to whichever
/// tile happened to draw it.
StatTile _tile(WidgetTester tester, String label) => tester
    .widgetList<StatTile>(find.byType(StatTile))
    .firstWhere((t) => t.label == label);

VerdictPill _pill(WidgetTester tester, String label) => tester
    .widgetList<VerdictPill>(find.byType(VerdictPill))
    .firstWhere((p) => p.label == label);

void main() {
  testWidgets('RunnersView prints the pool and what it rests on',
      (tester) async {
    final seen = <String>[];
    _tallViewport(tester);
    final api = RunnersApi(httpClient: MockClient((request) async {
      seen.add('${request.method} ${request.url.path}');
      return http.Response(jsonEncode(_rosterBody), 200,
          headers: {'content-type': 'application/json'});
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: RunnersView(api: api, alive: true))));
    await tester.pumpAndSettle();

    expect(seen, ['GET /api/runners']);
    expect(_tile(tester, 'Chain').value, 'intact');
    expect(_tile(tester, 'Chain').status, 'verified');
    // Two rows, one of them retired: the count comes off the rows rather
    // than off a number the engine also sends.
    expect(_tile(tester, 'Enrolled').value, '1');
    expect(_tile(tester, 'Queued').value, '4');
    expect(_tile(tester, 'Leased').value, '5');
    expect(_tile(tester, 'Tickets unspent').value, '3');
    // A lease lapses against the clock, so nothing runs to write the
    // moment it does. Colouring it is how a shrinking pool reads
    // differently from a slow one.
    expect(_tile(tester, 'Leases lapsed').value, '2');
    expect(_tile(tester, 'Leases lapsed').status, 'drift');

    expect(find.text('rnr-alpha'), findsOneWidget);
    expect(find.text('linux, gpu'), findsOneWidget);
    // Retiring is offered for a machine that is in the pool and withheld
    // for one already out of it.
    expect(find.byKey(const Key('runners-retire-rnr-alpha')), findsOneWidget);
    expect(find.byKey(const Key('runners-retire-rnr-beta')), findsNothing);
    expect(_pill(tester, 'retired').status, 'pending');

    expect(find.text('needs windows'), findsOneWidget);
    // Two jobs name the machine: the one it holds now and the one it
    // already finished. Dropping the name off a finished job would take
    // away the half an auditor reads it for.
    expect(find.text('held by rnr-alpha'), findsNWidgets(2));
    // A job that finished and failed is not a verified job, so `done`
    // alone never earns the verified colour.
    expect(_pill(tester, 'done').status, 'drift');
  });

  testWidgets('minting sends the granted labels and prints a refusal',
      (tester) async {
    final seen = <String>[];
    String? sent;
    _tallViewport(tester);
    final api = RunnersApi(httpClient: MockClient((request) async {
      seen.add('${request.method} ${request.url.path}');
      if (request.method == 'POST') {
        sent = request.body;
        return http.Response(jsonEncode(_refusalBody), 409,
            headers: {'content-type': 'application/json'});
      }
      return http.Response(jsonEncode(_rosterBody), 200,
          headers: {'content-type': 'application/json'});
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: RunnersView(api: api, alive: true))));
    await tester.pumpAndSettle();

    await tester.enterText(
        find.byKey(const Key('runners-ticket-id')), 'tkt-77');
    await tester.enterText(
        find.byKey(const Key('runners-ticket-labels')), ' linux , gpu ,');
    await tester.tap(find.byKey(const Key('runners-mint')));
    await tester.pumpAndSettle();

    expect(seen, [
      'GET /api/runners',
      'POST /api/runners/tickets',
      'GET /api/runners',
    ]);
    // Whitespace and a trailing separator are the operator's typing, not
    // a label the ticket grants.
    expect(jsonDecode(sent!), {
      'ticket_id': 'tkt-77',
      'labels': ['linux', 'gpu'],
    });
    // A 409 carries the engine's sentence; throwing on it would flatten
    // that to 'gateway returned 409'.
    expect(find.textContaining('Refused: the runner chain is broken'),
        findsOneWidget);
  });

  testWidgets('a broken chain withholds the rows and says so', (tester) async {
    _tallViewport(tester);
    final broken = Map<String, Object?>.from(_rosterBody)
      ..['chain_intact'] = false;
    final api = RunnersApi(httpClient: MockClient((request) async {
      return http.Response(jsonEncode(broken), 200,
          headers: {'content-type': 'application/json'});
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: RunnersView(api: api, alive: true))));
    await tester.pumpAndSettle();

    expect(_tile(tester, 'Chain').value, 'broken');
    expect(_tile(tester, 'Chain').status, 'drift');
    expect(find.textContaining('no longer verifies'), findsOneWidget);
    // Unverified membership is not drawn as membership.
    expect(find.text('rnr-alpha'), findsNothing);
    expect(find.text('held by rnr-alpha'), findsNothing);
    expect(find.byKey(const Key('runners-mint')), findsNothing);
  });

  testWidgets('RunnersView names the command when offline', (tester) async {
    final api = RunnersApi(httpClient: MockClient((request) async {
      throw StateError('offline surface must not call the engine');
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: RunnersView(api: api, alive: false))));
    expect(find.textContaining('engine is offline'), findsOneWidget);
    expect(find.text('flywheel up'), findsOneWidget);
  });
}
