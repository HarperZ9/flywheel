// The Swarms destination: typed API paths and payloads, honest empty
// states, receipt reading, and cancellation. The engine owns every
// rule; this surface only renders and issues.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_swarms.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/swarms_view.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _listBody = {
  'schema': 'flywheel.subagent-list/v1',
  'swarms': [
    {
      'swarm_id': 'swarm_abc123456789',
      'status': 'sealed',
      'verdict': 'satisfied',
      'completed': 2,
      'total': 2,
      'event_blocked': false,
    },
    {
      'swarm_id': 'swarm_det987654321',
      'status': 'detached',
      'children': 3,
    },
  ],
  'count': 2,
};

const _snapshotBody = {
  'swarm_id': 'swarm_abc123456789',
  'status': 'sealed',
  'receipt': {
    'swarm_id': 'swarm_abc123456789',
    'verdict': 'satisfied',
    'children': [
      {
        'child_id': 'sa_1111',
        'role': 'explore',
        'status': 'completed',
        'reattached': true,
      },
      {
        'child_id': 'sa_2222',
        'role': 'verify',
        'status': 'cancelled',
      },
    ],
  },
};

http.Response _json(Map<String, dynamic> body) => http.Response(
      jsonEncode(body),
      200,
      headers: {'content-type': 'application/json'},
    );

/// Drags the roster until [needle] is built; a lazy ListView never builds
/// children below the fold, so finders alone cannot reach them.
Future<void> _scrollToText(WidgetTester tester, String needle) async {
  for (var i = 0; i < 12; i++) {
    if (find.textContaining(needle).evaluate().isNotEmpty) return;
    await tester.drag(find.byType(ListView).first, const Offset(0, -250));
    await tester.pumpAndSettle();
  }
  fail('never scrolled to "$needle"');
}

void main() {
  test('SwarmsApi hits the documented routes and spawn payload', () async {
    final seen = <String>[];
    Map<String, dynamic>? spawnPayload;
    final api = SwarmsApi(
      httpClient: MockClient((request) async {
        seen.add('${request.method} ${request.url.path}');
        if (request.url.path == '/api/subagents/spawn') {
          spawnPayload = jsonDecode(request.body) as Map<String, dynamic>;
        }
        if (request.url.path == '/api/subagents/swarm') {
          expect(request.url.queryParameters['id'], 'swarm_x');
        }
        return _json(const {'ok': true});
      }),
    );

    await api.list();
    await api.snapshot('swarm_x');
    await api.cancel('swarm_y');
    await api.spawn(
      goal: 'map the auth module',
      endpoint: 'serve',
      children: const [
        {'role': 'explore'},
        {'role': 'verify'},
      ],
      quorumPolicy: 'any',
    );

    expect(
        seen,
        containsAll(<String>[
          'GET /api/subagents',
          'GET /api/subagents/swarm',
          'POST /api/subagents/cancel',
          'POST /api/subagents/spawn',
        ]));
    expect(spawnPayload?['goal'], 'map the auth module');
    expect(spawnPayload?['quorum_policy'], 'any');
    expect(spawnPayload?['children'], hasLength(2));
  });

  testWidgets('SwarmsView lists swarms and opens sealed receipts',
      (tester) async {
    var snapshotAsked = false;
    final api = SwarmsApi(
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/subagents/swarm') {
          snapshotAsked = true;
          return _json(_snapshotBody);
        }
        return _json(_listBody);
      }),
    );

    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: SwarmsView(api: api, alive: true))));
    await tester.pumpAndSettle();

    expect(find.text('swarm_abc123456789'), findsOneWidget);
    expect(find.text('swarm_det987654321'), findsOneWidget);
    expect(find.text('2 of 2 children completed'), findsOneWidget);
    // verdict pills render uppercased through the canon chip
    expect(find.text('SATISFIED'), findsOneWidget);

    await tester.tap(find.byKey(const Key('swarm-open-swarm_abc123456789')));
    await tester.pumpAndSettle();
    expect(snapshotAsked, isTrue);
    // the roster is a lazy ListView: drag until the appended detail builds
    await _scrollToText(tester, 'explore sa_1111');
    expect(find.textContaining('explore sa_1111'), findsOneWidget);
    expect(find.text('completed'), findsOneWidget);
    // a cancelled child stays visible as cancelled, never as success
    expect(find.text('cancelled'), findsOneWidget);
  });

  testWidgets('SwarmsView cancels a running swarm', (tester) async {
    final cancelled = <String>[];
    final api = SwarmsApi(
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/subagents/cancel') {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          cancelled.add(body['swarm_id'] as String);
          return _json({
            'swarm_id': body['swarm_id'],
            'state': 'cancelled',
            'killed': 1,
            'refused': 0,
          });
        }
        return _json(_listBody);
      }),
    );

    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: SwarmsView(api: api, alive: true))));
    await tester.pumpAndSettle();

    // detached swarms are cancellable from this surface; bring the row
    // into view before tapping, the roster can exceed the test viewport
    await tester.ensureVisible(
        find.byKey(const Key('swarm-cancel-swarm_det987654321')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('swarm-cancel-swarm_det987654321')));
    await tester.pumpAndSettle();
    expect(cancelled, ['swarm_det987654321']);
  });

  testWidgets('SwarmsView names the command when the engine is offline',
      (tester) async {
    final api = SwarmsApi(httpClient: MockClient((request) async {
      throw StateError('must not be called while offline');
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: SwarmsView(api: api, alive: false))));
    expect(find.textContaining('engine is offline'), findsOneWidget);
    expect(find.text('flywheel up'), findsOneWidget);
  });
}
