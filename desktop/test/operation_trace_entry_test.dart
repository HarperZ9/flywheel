import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/operation_trace_entry.dart';
import 'agent_trace_models_test.dart' show fixture, operation, journey;

OperationResult result() => OperationResult.fromJson({
      'schema': operationResultSchema,
      'operation_ref': operation,
      'action': 'agent.run',
      'state': 'completed',
      'result': fixture('detail_projection'),
    });
OperationSnapshot snapshot(OperationResult result, {String? head}) =>
    OperationSnapshot.fromJson({
      'schema': operationSnapshotSchema,
      'operation_ref': operation,
      'journey_ref': journey,
      'state': 'completed',
      'event_head_sha256': 'a' * 64,
      'can_cancel': false,
      'terminal_event_ref': 'b' * 64,
      'result_sha256': head ?? result.canonicalSha256,
    });

void main() {
  testWidgets('only current running progress offers a read without fetching',
      (tester) async {
    var reads = 0;
    final client = GatewayClient(httpClient: MockClient((_) async {
      reads++;
      return http.Response('', 404);
    }));
    final running = OperationSnapshot.fromJson({
      'schema': operationSnapshotSchema,
      'operation_ref': operation,
      'journey_ref': journey,
      'state': 'running',
      'event_head_sha256': 'a' * 64,
      'can_cancel': true,
      'terminal_event_ref': null,
      'result_sha256': null,
    });
    final valid = fixture('running');
    for (final progress in [
      valid,
      {...valid, 'operation_ref': 'op_${'a' * 32}'},
      {...valid, 'journey_ref': 'jrn_${'a' * 32}'},
      fixture('completed'),
    ]) {
      await tester.pumpWidget(MaterialApp(
          theme: flywheelLightTheme(),
          home: Scaffold(
              body: OperationTraceEntry(
                  client: client, snapshot: running, progress: [progress]))));
      expect(find.byType(TextButton),
          identical(progress, valid) ? findsOneWidget : findsNothing);
      expect(reads, 0);
    }
    client.close();
  });
  testWidgets(
      'sealed result opens opt-in private reader; narrow layout remains usable',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    var reads = 0;
    final client = GatewayClient(httpClient: MockClient((request) async {
      expect(request.method, 'GET');
      reads++;
      return http.Response(jsonEncode(fixture('detail')), 200,
          headers: {'content-type': 'application/json; charset=utf-8'});
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: OperationTraceEntry(
                client: client,
                snapshot: snapshot(result()),
                result: result(),
                progress: const []))));
    await tester.tap(find.textContaining('Private trace ·'));
    await tester.pumpAndSettle();
    expect(reads, 0);
    await tester.ensureVisible(find.text('Read private trace'));
    await tester.tap(find.text('Read private trace'));
    await tester.pumpAndSettle();
    expect(reads, 1);
    expect(find.textContaining('naïve ✓'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.tap(find.text('Close private trace'));
    await tester.pumpAndSettle();
    expect(find.textContaining('naïve ✓'), findsNothing);
    client.close();
  });

  testWidgets('wrong sealed result hash cannot open or request a private trace',
      (tester) async {
    var reads = 0;
    final client = GatewayClient(httpClient: MockClient((_) async {
      reads++;
      return http.Response('', 404);
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: OperationTraceEntry(
                client: client,
                snapshot: snapshot(result(), head: 'c' * 64),
                result: result(),
                progress: const []))));
    expect(
        find.textContaining('operation result did not match'), findsOneWidget);
    expect(find.byType(TextButton), findsNothing);
    expect(reads, 0);
    client.close();
  });
}
