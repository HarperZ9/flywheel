// The Browser destination: what a run was allowed to drive, and what it
// actually did. Two counts carry the page. Refused is kept, so a tightly
// bounded run and a run that did nothing do not read alike afterwards.
// Performed is separate from admitted, so an act allowed on an engine
// with no driver bound reads as a decision recorded rather than a screen
// that moved.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_browser.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/browser_view.dart';
import 'package:flywheel_desktop/widgets/fw.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _unboundRoster = {
  'schema': 'flywheel.browser-roster/v1',
  'read_at': '2026-09-06T09:00:00Z',
  'driver': null,
  'sessions': ['run-decided', 'run-driven'],
};

const _boundRoster = {
  'schema': 'flywheel.browser-roster/v1',
  'read_at': '2026-09-06T09:00:00Z',
  'driver': 'chromedriver-141',
  'sessions': ['run-decided', 'run-driven'],
};

const _decided = {
  'schema': 'flywheel.browser-session/v1',
  'read_at': '2026-09-06T09:00:00Z',
  'run_id': 'run-decided',
  'chain_intact': true,
  'policy': {
    'origins': ['https://example.org'],
    'refuse_kinds': ['type'],
    'max_actions': 20,
  },
  'open_origin': 'https://example.org',
  'driver': null,
  'actions': [
    {
      'kind': 'action',
      'at': '2026-09-06T08:58:00Z',
      'run_id': 'run-decided',
      'seq': 1,
      'action': {'kind': 'open', 'url': 'https://example.org/docs'},
      'admitted': true,
      'reason': null,
      'origin': 'https://example.org',
      'driver': null,
      'performed': false,
      'result_sha256': null,
    },
    {
      'kind': 'action',
      'at': '2026-09-06T08:58:30Z',
      'run_id': 'run-decided',
      'seq': 2,
      'action': {'kind': 'type', 'field': 'password'},
      'admitted': false,
      'reason': 'credential-shaped field',
      'origin': 'https://example.org',
      'driver': null,
      'performed': false,
      'result_sha256': null,
    },
  ],
  'attempted': 2,
  'admitted': 1,
  'refused': 1,
  'performed': 0,
};

const _driven = {
  'schema': 'flywheel.browser-session/v1',
  'read_at': '2026-09-06T09:00:00Z',
  'run_id': 'run-driven',
  'chain_intact': true,
  'policy': {
    'origins': ['https://example.org'],
    'refuse_kinds': <String>[],
    'max_actions': null,
  },
  'open_origin': 'https://example.org',
  'driver': 'chromedriver-141',
  'actions': [
    {
      'kind': 'action',
      'at': '2026-09-06T08:59:00Z',
      'run_id': 'run-driven',
      'seq': 1,
      'action': {'kind': 'click', 'selector': '#save'},
      'admitted': true,
      'reason': null,
      'origin': 'https://example.org',
      'driver': 'chromedriver-141',
      'performed': true,
      'result_sha256':
          'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    },
  ],
  'attempted': 1,
  'admitted': 1,
  'refused': 0,
  'performed': 1,
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

http.Response _json(Object body) => http.Response(jsonEncode(body), 200,
    headers: {'content-type': 'application/json'});

void main() {
  testWidgets('an unbound driver reads as recorded, never as performed',
      (tester) async {
    final seen = <String>[];
    _tallViewport(tester);
    final api = BrowserApi(httpClient: MockClient((request) async {
      seen.add('${request.method} ${request.url.path}');
      return request.url.path == '/api/browser'
          ? _json(_unboundRoster)
          : _json(_decided);
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: BrowserView(api: api, alive: true))));
    await tester.pumpAndSettle();

    expect(seen, ['GET /api/browser', 'GET /api/browser/run-decided']);
    expect(
        find.textContaining('No driver is bound'), findsOneWidget);

    expect(_tile(tester, 'Chain').value, 'intact');
    expect(_tile(tester, 'Attempted').value, '2');
    expect(_tile(tester, 'Admitted').value, '1');
    // Kept rather than folded into attempted: a bounded run and a run
    // that did nothing print the same admitted count otherwise.
    expect(_tile(tester, 'Refused').value, '1');
    expect(_tile(tester, 'Refused').status, 'pending');
    // The act the policy allowed still moved no screen.
    expect(_tile(tester, 'Performed').value, '0');

    // The rules, drawn as they were written: the origin allowed, the
    // kind refused outright.
    expect(_pill(tester, 'https://example.org').status, 'verified');
    expect(_pill(tester, 'type').status, 'drift');
    expect(find.textContaining('Session cap 20'), findsOneWidget);

    expect(find.text('https://example.org/docs'), findsOneWidget);
    expect(find.text('recorded'), findsOneWidget);
    expect(find.text('performed'), findsNothing);
    expect(find.text('credential-shaped field'), findsOneWidget);
  });

  testWidgets('picking another session reads that one', (tester) async {
    final seen = <String>[];
    _tallViewport(tester);
    final api = BrowserApi(httpClient: MockClient((request) async {
      seen.add('${request.method} ${request.url.path}');
      if (request.url.path == '/api/browser') return _json(_boundRoster);
      return request.url.path.endsWith('run-driven')
          ? _json(_driven)
          : _json(_decided);
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: BrowserView(api: api, alive: true))));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('browser-session-run-driven')));
    await tester.pumpAndSettle();

    expect(seen, [
      'GET /api/browser',
      'GET /api/browser/run-decided',
      'GET /api/browser/run-driven',
    ]);
    expect(_pill(tester, 'driver bound').status, 'live');
    expect(find.text('chromedriver-141'), findsOneWidget);
    expect(_tile(tester, 'Performed').value, '1');
    expect(_tile(tester, 'Refused').value, '0');
    // Nothing colours a zero refusal count, so a run that was never told
    // no does not borrow the look of one that was.
    expect(_tile(tester, 'Refused').status, isNull);
    expect(find.text('performed'), findsOneWidget);
    expect(find.textContaining('No session cap'), findsOneWidget);
    expect(find.textContaining('No kind of act is refused outright'),
        findsOneWidget);
  });

  testWidgets('no session opened is said, not drawn as an empty page',
      (tester) async {
    _tallViewport(tester);
    final api = BrowserApi(httpClient: MockClient((request) async {
      return _json({
        'schema': 'flywheel.browser-roster/v1',
        'read_at': '2026-09-06T09:00:00Z',
        'driver': null,
        'sessions': <String>[],
      });
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: BrowserView(api: api, alive: true))));
    await tester.pumpAndSettle();

    expect(find.textContaining('No session has been opened'), findsOneWidget);
    expect(find.byType(StatTile), findsNothing);
  });

  testWidgets('BrowserView names the command when offline', (tester) async {
    final api = BrowserApi(httpClient: MockClient((request) async {
      throw StateError('offline surface must not call the engine');
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: BrowserView(api: api, alive: false))));
    expect(find.textContaining('engine is offline'), findsOneWidget);
    expect(find.text('flywheel up'), findsOneWidget);
  });
}
