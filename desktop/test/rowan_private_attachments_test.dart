import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_auth.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/canonical_json.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/operation_private_attachments.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'agent_caption_fixtures.dart';

Map<String, dynamic> _projectionJson(
  List<Map<String, dynamic>> pages, {
  String state = 'completed',
  String? journey,
}) {
  final raw = captionFixture('detail_projection')..remove('projection_sha256');
  raw['record_count'] = pages.length;
  raw['state'] = state;
  raw['trace_head_sha256'] =
      (pages.last['record'] as Map)['record_sha256'] as String;
  if (journey != null) raw['journey_ref'] = journey;
  return {...raw, 'projection_sha256': canonicalJsonSha256(raw)};
}

OperationResult _result(Map<String, dynamic> projection) =>
    OperationResult.fromJson({
      'schema': operationResultSchema,
      'operation_ref': projection['operation_ref'],
      'action': 'agent.run',
      'state': 'completed',
      'result': projection,
    });

OperationSnapshot _snapshot(Map<String, dynamic> projection, String hash) =>
    OperationSnapshot.fromJson({
      'schema': operationSnapshotSchema,
      'operation_ref': projection['operation_ref'],
      'journey_ref': projection['journey_ref'],
      'event_head_sha256': 'a' * 64,
      'state': 'completed',
      'can_cancel': false,
      'terminal_event_ref': 'b' * 64,
      'result_sha256': hash,
    });

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void main() {
  testWidgets('Rowan operation exposes private trace and opt-in captions',
      (tester) async {
    var reads = 0;
    Map<String, String>? traceHeaders;
    final pages = captionPages([
      captionLedger('assistant', 'private caption from authenticated trace')
    ]);
    final projection = _projectionJson(pages);
    final result = _result(projection);
    final snapshot = _snapshot(projection, result.canonicalSha256);
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: AuthedClient(
        MockClient((request) async {
          expect(request.method, 'GET');
          expect(request.url.path,
              '/api/operations/${snapshot.operationRef}/trace');
          expect(request.url.queryParameters['sequence'], '0');
          reads++;
          traceHeaders = request.headers;
          return http.Response(jsonEncode(pages.single), 200,
              headers: {'content-type': 'application/json'});
        }),
        readToken: () => 'host-bearer-token',
      ),
    );

    await tester.pumpWidget(_wrap(OperationPrivateAttachments(
      client: client,
      snapshot: snapshot,
      result: result,
      progress: const [],
    )));

    expect(find.textContaining('Private trace · completed · 1 records'),
        findsOneWidget);
    expect(find.text('Start private captions'), findsOneWidget);
    expect(reads, 0);

    await tester.tap(find.text('Start private captions'));
    await tester.pumpAndSettle();

    expect(reads, 1);
    expect(traceHeaders?['Authorization'], 'Bearer host-bearer-token');
    expect(
        find.text('private caption from authenticated trace'), findsOneWidget);
    client.close();
  });

  testWidgets('stale or cross-Journey trace metadata never mounts captions',
      (tester) async {
    var reads = 0;
    final pages = captionPages([captionLedger('assistant', 'wrong journey')]);
    final projection = _projectionJson(
      pages,
      journey: 'jrn_${'f' * 32}',
    );
    final result = _result(projection);
    final snapshot = _snapshot(
      {...projection, 'journey_ref': 'jrn_${'e' * 32}'},
      result.canonicalSha256,
    );
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((_) async {
        reads++;
        return http.Response('{}', 500);
      }),
    );

    await tester.pumpWidget(_wrap(OperationPrivateAttachments(
      client: client,
      snapshot: snapshot,
      result: result,
      progress: const [],
    )));

    expect(find.textContaining('metadata did not match'), findsOneWidget);
    expect(find.text('Start private captions'), findsNothing);
    expect(reads, 0);
    client.close();
  });
}
