// The Peers destination: what the observer can honestly say about sessions it
// did not run. The bodies come from peer_sessions_fixture.dart, generated from
// the engine route, so a field asserted here is a field the engine emits. Two
// things are load-bearing and tested as such: a mailbox body never reaches the
// surface, and freshness never gets a verdict color, because a file written a
// minute ago is no evidence that a session is running.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/peer_sessions_view.dart';
import 'package:flywheel_desktop/widgets/fw.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'peer_sessions_fixture.dart';

/// The message body the fixture mailbox was written with. The route is built so
/// this never crosses it; the test fails if it ever appears on the surface.
const _body =
    'status: the observer slice is written and its gates are green';

/// A viewport tall enough to build every row, so a failed assertion means the
/// surface omitted something rather than the list not having scrolled to it.
void _tallViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1400, 3200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

Map<String, dynamic> _fixture(String path) =>
    jsonDecode(peerSessionsFixture[path]!) as Map<String, dynamic>;

/// Serve the fixture, with per-path edits applied to the decoded body. Editing
/// a value keeps the field names the engine really emits.
GatewayClient _client(
  List<String> seen, {
  Map<String, void Function(Map<String, dynamic>)> edit = const {},
}) {
  return GatewayClient(httpClient: MockClient((request) async {
    final path = request.url.path;
    seen.add(path);
    final body = _fixture(path);
    edit[path]?.call(body);
    return http.Response(jsonEncode(body), 200,
        headers: {'content-type': 'application/json'});
  }));
}

Future<void> _pump(
  WidgetTester tester,
  GatewayClient client, {
  bool alive = true,
}) async {
  await tester.pumpWidget(MaterialApp(
    theme: flywheelLightTheme(),
    home: Scaffold(body: PeerSessionsView(client: client, alive: alive)),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the surface reads all three routes and prints what each supports',
      (tester) async {
    _tallViewport(tester);
    final seen = <String>[];
    await _pump(tester, _client(seen));

    expect(
        seen..sort(),
        <String>[
          '/api/peer-sessions',
          '/api/peer-sessions/journey',
          '/api/peer-sessions/mailbox',
        ]);

    // the registry counts, with the denominator beside the numerator
    expect(find.text('2 of 2'), findsOneWidget);
    expect(find.text('TRANSCRIPTS FOUND'), findsOneWidget);
    expect(find.textContaining('0 left unread at this limit'), findsOneWidget);
    expect(find.textContaining('registry a7191d30b5de9467'), findsOneWidget);

    // one card per harness, each naming the id it read from the content
    expect(find.text('codex'), findsOneWidget);
    expect(find.text('claude_code'), findsOneWidget);
    expect(find.text('01a0aaaa-bbbb'), findsOneWidget);
    expect(find.text('5f0c1e2a-1111'), findsOneWidget);

    // Age is stated in the unit that fits, and never as a claim about running.
    // The engine's own statement also names the activity class, so the meta
    // lines are collected first and counted, rather than searched for text that
    // appears twice on the surface for two different reasons.
    final ages = tester
        .widgetList<Text>(find.byType(Text))
        .map((t) => t.data ?? '')
        .where((s) => s.contains('since last write'))
        .toList();
    expect(ages, hasLength(2));
    expect(ages.where((s) => s.contains('2m since last write')), hasLength(1));
    expect(ages.where((s) => s.contains('48h since last write')), hasLength(1));
    expect(ages.where((s) => s.contains('class recent')), hasLength(1));
    expect(ages.where((s) => s.contains('class stale')), hasLength(1));

    // the mailbox row is a header and a receipt
    expect(find.text('codex.root to claude.fable'), findsOneWidget);
    expect(find.text('MATCH'), findsOneWidget);
    expect(find.textContaining('62 chars'), findsOneWidget);
    expect(find.textContaining('body 315d8407bbf23b0b'), findsOneWidget);

    // the limit of the whole surface, carried on the surface
    expect(find.textContaining('Whether any session is running'),
        findsOneWidget);
  });

  testWidgets('a message body never reaches the surface', (tester) async {
    _tallViewport(tester);
    await _pump(tester, _client(<String>[]));

    // the fixture body really is the body of the message that was listed
    expect(_fixture('/api/peer-sessions/mailbox')['messages'], hasLength(1));
    expect(find.textContaining(_body), findsNothing);
    expect(find.textContaining('observer slice'), findsNothing);
  });

  testWidgets('freshness is printed as text and never as a verdict',
      (tester) async {
    _tallViewport(tester);
    await _pump(tester, _client(<String>[]));

    // color is a verdict in this system. Two sessions were read and neither
    // carries an issue, so the only pill on the surface is the mailbox receipt.
    final pills = tester.widgetList<VerdictPill>(find.byType(VerdictPill));
    expect(pills.map((p) => p.label), <String>['MATCH']);
    expect(find.text('RECENT'), findsNothing);
    expect(find.text('STALE'), findsNothing);
  });

  testWidgets('an issue on a session prints as drift', (tester) async {
    _tallViewport(tester);
    final client = _client(<String>[], edit: {
      '/api/peer-sessions/journey': (body) {
        final events = body['events'] as List;
        final facts = (events[1] as Map)['payload']['facts'] as List;
        (facts[0] as Map)['issues'] = ['session_meta_absent_in_head'];
      },
    });
    await _pump(tester, client);

    expect(find.text('SESSION_META_ABSENT_IN_HEAD'), findsOneWidget);
    final pills = tester.widgetList<VerdictPill>(find.byType(VerdictPill));
    expect(pills.where((p) => p.status == 'drift'), hasLength(1));
  });

  testWidgets('an id that is not id shaped is named rather than printed',
      (tester) async {
    _tallViewport(tester);
    final client = _client(<String>[], edit: {
      '/api/peer-sessions/journey': (body) {
        final events = body['events'] as List;
        final facts = (events[1] as Map)['payload']['facts'] as List;
        (facts[0] as Map)['session_ref'] = null;
      },
    });
    await _pump(tester, client);

    expect(find.text('id not id-shaped'), findsOneWidget);
    expect(find.text('01a0aaaa-bbbb'), findsNothing);
  });

  testWidgets('a renamed mailbox file is called a disagreement, not a match',
      (tester) async {
    _tallViewport(tester);
    final client = _client(<String>[], edit: {
      '/api/peer-sessions/mailbox': (body) {
        final row = (body['messages'] as List)[0] as Map;
        row['file_name_consistent'] = false;
        row['receipt_state'] = 'DRIFT';
      },
    });
    await _pump(tester, client);

    expect(find.text('DRIFT'), findsOneWidget);
    expect(find.text('MATCH'), findsNothing);
    expect(
        find.text('the file name disagrees with the header inside it'),
        findsOneWidget);
  });

  testWidgets('an empty mailbox reads as a state rather than a failure',
      (tester) async {
    _tallViewport(tester);
    final client = _client(<String>[], edit: {
      '/api/peer-sessions/mailbox': (body) {
        body['mailbox_present'] = false;
        body['messages'] = <dynamic>[];
        body['listed'] = 0;
        body['matched'] = 0;
      },
    });
    await _pump(tester, client);

    expect(find.textContaining('No mailbox directory exists yet'),
        findsOneWidget);
    expect(find.textContaining('Failed:'), findsNothing);
  });

  testWidgets('nothing read means nothing claimed about whether a peer exists',
      (tester) async {
    _tallViewport(tester);
    final client = _client(<String>[], edit: {
      '/api/peer-sessions/journey': (body) {
        body['events'] = [(body['events'] as List).first];
      },
      '/api/peer-sessions': (body) {
        body['sessions'] = <dynamic>[];
        body['observed_count'] = 0;
        body['unobserved_count'] = 2;
      },
    });
    await _pump(tester, client);

    expect(find.text('0 of 2'), findsOneWidget);
    expect(find.textContaining('Nothing is claimed about'), findsOneWidget);
  });

  testWidgets('a transcript that could not be read carries the drift color',
      (tester) async {
    _tallViewport(tester);
    final client = _client(<String>[], edit: {
      '/api/peer-sessions': (body) => body['observe_failures'] = 1,
    });
    await _pump(tester, client);

    final failures = tester
        .widgetList<StatTile>(find.byType(StatTile))
        .firstWhere((t) => t.label == 'read failures');
    expect(failures.value, '1');
    expect(failures.status, 'drift');
  });

  // The same tile carries no verdict at zero, so the color is the finding and
  // not the label. This is a separate case because pumping a second view of the
  // same type updates the state that is already there rather than building a
  // new one, and the surface only reloads when the engine comes back alive.
  testWidgets('the read-failures tile stays uncolored when nothing failed',
      (tester) async {
    _tallViewport(tester);
    await _pump(tester, _client(<String>[]));

    final clean = tester
        .widgetList<StatTile>(find.byType(StatTile))
        .firstWhere((t) => t.label == 'read failures');
    expect(clean.value, '0');
    expect(clean.status, isNull);
  });

  testWidgets('a refusing engine prints its message and stops there',
      (tester) async {
    _tallViewport(tester);
    final client = GatewayClient(httpClient: MockClient((request) async {
      return http.Response('{"error":{"code":"FORBIDDEN"}}', 403,
          headers: {'content-type': 'application/json'});
    }));
    await _pump(tester, client);

    expect(find.textContaining('Failed:'), findsOneWidget);
    expect(find.byType(VerdictPill), findsNothing);
  });

  testWidgets('the offline surface names the command and calls no route',
      (tester) async {
    final client = GatewayClient(httpClient: MockClient((request) async {
      throw StateError('the offline surface must not reach the engine');
    }));
    await _pump(tester, client, alive: false);

    expect(find.textContaining('engine is offline'), findsOneWidget);
    expect(find.text('flywheel up'), findsOneWidget);
  });
}
