// The Scan destination: the counts, and the three things that make an
// empty count mean anything. A scan that found nothing and a scan that
// looked at nothing print the same number, so the corpus, the ruleset
// proof, and the suppressions are asserted here alongside the verdict.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_scan.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/scan_view.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _rosterBody = {
  'schema': 'flywheel.scan-roster/v1',
  'read_at': '2026-09-06T09:00:00Z',
  'scans': 3,
  'chain_intact': true,
  'head_sha256':
      'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  'latest': {
    'schema': 'flywheel.code-scan/v1',
    'scanned_at': '2026-09-06T08:59:00Z',
    'trees': ['harness', 'scripts'],
    'ruleset_proven': true,
    'files_in_corpus': 1305,
    'files_scanned': 1304,
    'skipped': ['harness/broken_encoding.py'],
    'counts': {'high': 2, 'medium': 1, 'low': 4},
    'suppressed_count': 5,
    'clean': false,
    'findings': [
      {
        'rule_id': 'shell-true',
        'severity': 'high',
        'path': 'harness/witness.py',
        'line': 35,
      },
      {
        'rule_id': 'weak-hash',
        'severity': 'low',
        'path': 'harness/legacy_digest.py',
        'line': 12,
      },
    ],
    'findings_total': 7,
    'findings_truncated': 0,
  },
  'verify': {
    'record_sealed': true,
    'corpus_matches': true,
    'ruleset_matches': false,
  },
};

const _refusalBody = {
  'schema': 'flywheel.scan-ack/v1',
  'scanned': false,
  'refused': 'the scan chain is broken',
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

void main() {
  testWidgets('ScanView prints the counts and what they rest on',
      (tester) async {
    final seen = <String>[];
    _tallViewport(tester);
    final api = ScanApi(httpClient: MockClient((request) async {
      seen.add('${request.method} ${request.url.path}');
      return http.Response(jsonEncode(_rosterBody), 200,
          headers: {'content-type': 'application/json'});
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: ScanView(api: api, alive: true))));
    await tester.pumpAndSettle();

    expect(seen, ['GET /api/scan/vulnerabilities']);
    // open findings, so the word clean is not printed
    expect(find.text('open'), findsOneWidget);
    expect(find.text('SUPPRESSED'), findsOneWidget);
    // the seals, each answered separately; a stale ruleset shows as drift
    expect(find.text('RULES PROVED'), findsOneWidget);
    expect(find.text('CHAIN INTACT'), findsOneWidget);
    expect(find.text('RULESET MATCHES'), findsOneWidget);
    // the corpus, with the hole in it named rather than rounded away
    expect(find.textContaining('1304 of 1305 files read'), findsOneWidget);
    expect(find.textContaining('harness, scripts'), findsOneWidget);
    expect(find.textContaining('corpus has a hole in it'), findsOneWidget);
    // findings carry their site; the count covers every one of them
    expect(find.text('harness/witness.py:35'), findsOneWidget);
    expect(find.text('shell-true'), findsOneWidget);
    expect(find.textContaining('5 further finding(s) are counted above'),
        findsOneWidget);
  });

  testWidgets('a refused scan prints the engine reason, not a status code',
      (tester) async {
    _tallViewport(tester);
    final api = ScanApi(httpClient: MockClient((request) async {
      if (request.method == 'POST') {
        return http.Response(jsonEncode(_refusalBody), 409,
            headers: {'content-type': 'application/json'});
      }
      return http.Response(jsonEncode(_rosterBody), 200,
          headers: {'content-type': 'application/json'});
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: ScanView(api: api, alive: true))));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('scan-run')));
    await tester.pumpAndSettle();

    // a 409 carries the reason the engine gives; throwing on it would
    // flatten that to 'gateway returned 409'
    expect(find.textContaining('Refused: the scan chain is broken'),
        findsOneWidget);
  });

  testWidgets('ScanView names the command when offline', (tester) async {
    final api = ScanApi(httpClient: MockClient((request) async {
      throw StateError('offline surface must not call the engine');
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: ScanView(api: api, alive: false))));
    expect(find.textContaining('engine is offline'), findsOneWidget);
    expect(find.text('flywheel up'), findsOneWidget);
  });
}
