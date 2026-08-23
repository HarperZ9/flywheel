// Receipts view truth: an inclusion proof is present_unchecked until THIS
// device recomputes the Merkle root. A served proof object must never read
// as verified on arrival, and a tampered root must render drift, not MATCH.
// Faked HTTP, no network.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/receipts_view.dart';

const _leaf =
    '0000000000000000000000000000000000000000000000000000000000000003';
const _root =
    'c48c0df7d9b37592c69ba5ca2afc8ada511550e607e6dfe7fdef6b85d89f5269';

Map<String, dynamic> _ledgerJson() => {
      'catalog': [],
      'catalog_present': 0,
      'envelopes': [
        {
          'name': 'envelope-demo.json',
          'verdict': 'PASS',
          'task_id': 't1',
          'sha256': _leaf,
        }
      ],
      'envelope_count': 1,
      'pass_count': 1,
    };

Map<String, dynamic> _proofV2({String? merkleRoot}) => {
      'schema': 'flywheel.receipts-proof/v2',
      'leaf': _leaf,
      'index': 2,
      'tree_size': 5,
      'merkle_root': merkleRoot ?? _root,
      'audit_path': [
        {
          'hash':
              '82f02cf2ac0074619e6d747c35e08b29431a16943ddf81cfd9065c004ee6364a',
          'side': 'right',
        },
        {
          'hash':
              '0971c8a1ce81287ccbc95aa4f171a5f807fb13ea2118f56b99769459a64906ad',
          'side': 'left',
        },
        {
          'hash':
              '086fb60bd968fe68ecec6a8d826ea5aa7d3d8020e644d7c5d0e07ded456ca3e8',
          'side': 'right',
        },
      ],
    };

GatewayClient _client(Map<String, dynamic> Function(Uri) respond) =>
    GatewayClient(
      baseUrl: 'http://127.0.0.1:8799',
      httpClient: MockClient((request) async {
        final body = respond(request.url);
        return http.Response(jsonEncode(body), 200,
            headers: {'content-type': 'application/json'});
      }),
    );

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: child),
    );

void main() {
  testWidgets('an honest proof recomputes to MATCH on this device',
      (tester) async {
    final client = _client((uri) =>
        uri.path == '/api/receipts/proof' ? _proofV2() : _ledgerJson());
    await tester.pumpWidget(_wrap(ReceiptsView(
        client: client, alive: true, focusLeaf: _leaf)));
    await tester.pumpAndSettle();

    expect(find.text('INCLUDED'), findsOneWidget,
        reason: 'the recompute landed on the advertised root');
    expect(find.textContaining('recomputed'), findsWidgets,
        reason: 'MATCH must name that this device recomputed it');
  });

  testWidgets('a tampered advertised root never reads verified',
      (tester) async {
    final tampered = 'f' * 63 + '0';
    final client = _client((uri) =>
        uri.path == '/api/receipts/proof'
            ? _proofV2(merkleRoot: tampered)
            : _ledgerJson());
    await tester.pumpWidget(_wrap(ReceiptsView(
        client: client, alive: true, focusLeaf: _leaf)));
    await tester.pumpAndSettle();

    expect(find.text('INCLUDED'), findsNothing,
        reason: 'presence of a proof object is not verification');
    expect(find.text('DRIFT'), findsOneWidget,
        reason: 'a mismatching root renders as an honest drift');
  });

  testWidgets('receipt presence in the ledger alone stays unchecked',
      (tester) async {
    final client = _client((uri) => _ledgerJson());
    await tester.pumpWidget(
        _wrap(ReceiptsView(client: client, alive: true)));
    await tester.pumpAndSettle();

    expect(find.text('INCLUDED'), findsNothing,
        reason: 'no proof was fetched; nothing may claim inclusion');
  });
}
