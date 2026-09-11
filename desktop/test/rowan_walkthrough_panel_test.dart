import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/rowan_walkthrough_panel.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _a = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _head =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _event =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _operation = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _binding = GatewayJourneyBinding('jrn_$_a', _head);
const _grant = 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _answer =
    'The implementation is off-by-one: next_attempt 4 with max_attempts 3 '
    'is allowed, but the rule is next_attempt <= max_attempts.';

void main() {
  testWidgets('walkthrough dispatches supervised run and gates follow-up',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1000, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final result = OperationResult.fromJson({
      'schema': operationResultSchema,
      'operation_ref': _operation,
      'action': 'agent.run',
      'state': 'completed',
      'result': {'final': _answer},
    });
    final terminal = _snapshot(result.canonicalSha256);
    final client = _client(
      agentBody: _sse(terminal, result),
      snapshotBody: terminal,
    );
    Map<String, dynamic>? dispatched;
    var followUpReviewed = false;

    await tester.pumpWidget(_wrap(GatewayOperationScope(
      authorize: (_, operation, currentOperation, dispatch) async {
        if (currentOperation() != operation) return null;
        dispatched = operation.finalBody(_binding, _grant);
        return dispatch(dispatched!);
      },
      child: RowanWalkthroughPanel(
        client: client,
        alive: true,
        currentBinding: _binding,
        captionBuilder: (_, __) => const Text('caption seam attached'),
        onReviewFollowUp: (_, __) async => followUpReviewed = true,
      ),
    )));
    await tester.pumpAndSettle();

    expect(find.text('Rowan live walkthrough'), findsOneWidget);
    expect(find.textContaining(_binding.journeyRef), findsOneWidget);
    expect(find.text('caption seam attached'), findsOneWidget);
    expect(find.textContaining('Hidden internal chain-of-thought'),
        findsOneWidget);
    expect(find.textContaining('Guidance pause does not stop execution'),
        findsOneWidget);
    expect(_runButton(tester).onPressed, isNull);

    await tester.enterText(
      find.byKey(const Key('rowan-walkthrough-root')),
      r'C:\synthetic\repo',
    );
    await tester.tap(find.text('default model'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('qwen2.5-coder-14b-instruct'));
    await tester.pumpAndSettle();
    expect(_runButton(tester).onPressed, isNotNull);

    await tester.tap(find.widgetWithText(FilledButton, 'Run'));
    await tester.pumpAndSettle();

    expect(dispatched?['journey_ref'], _binding.journeyRef);
    expect(dispatched?['expected_event_head'], _binding.eventHead);
    expect(dispatched?['endpoint'], 'ollama');
    expect(dispatched?['model'], 'qwen2.5-coder-14b-instruct');
    expect(dispatched?['root'], r'C:\synthetic\repo');
    expect(dispatched?['allow_write'], isFalse);
    expect(dispatched?['allow_exec'], isFalse);
    expect(dispatched?['max_steps'], 3);
    expect(dispatched?['max_tokens'], 1024);
    expect(dispatched?['timeout_s'], 300);
    expect(dispatched!.containsKey('oracle'), isFalse);
    expect(dispatched!.containsKey('expected_defect'), isFalse);
    expect(find.textContaining('independent oracle matched'), findsOneWidget);
    expect(find.widgetWithText(OutlinedButton, 'Review bounded follow-up'),
        findsNothing);

    await tester.tap(find.widgetWithText(OutlinedButton, 'Reopen operation'));
    await tester.pumpAndSettle();
    expect(
        find.textContaining('same operation record reopened'), findsOneWidget);

    await tester
        .tap(find.widgetWithText(OutlinedButton, 'Review bounded follow-up'));
    await tester.pumpAndSettle();
    expect(followUpReviewed, isTrue);
  });

  testWidgets('missing Journey binding blocks execution with an honest reason',
      (tester) async {
    await tester.pumpWidget(_wrap(RowanWalkthroughPanel(
      client: _client(agentBody: '', snapshotBody: const {}),
      alive: true,
    )));
    await tester.pumpAndSettle();

    expect(find.textContaining('Select a Journey before approval'),
        findsOneWidget);
    expect(_runButton(tester).onPressed, isNull);
  });
}

FilledButton _runButton(WidgetTester tester) => tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Run'),
    );

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

GatewayClient _client({
  required String agentBody,
  required Map<String, Object?> snapshotBody,
}) =>
    GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        switch (request.url.path) {
          case '/api/endpoints':
            return http.Response(
              '{"rows":[{"name":"ollama","backend":"local",'
              '"credential":"local-none","provider_role":"local",'
              '"configured":true}]}',
              200,
            );
          case '/api/models':
            return http.Response(
              jsonEncode({
                'endpoint': 'ollama',
                'models': [
                  {'id': 'qwen2.5-coder-14b-instruct', 'default': false},
                ],
                'reason': '',
              }),
              200,
            );
          case '/api/agent':
            return http.Response(agentBody, 200);
          case '/api/operations/$_operation':
            return http.Response(jsonEncode(snapshotBody), 200);
        }
        return http.Response('{"error":"unexpected ${request.url.path}"}', 500);
      }),
    );

Map<String, Object?> _snapshot(String resultSha256) => {
      'schema': operationSnapshotSchema,
      'operation_ref': _operation,
      'journey_ref': _binding.journeyRef,
      'event_head_sha256': _event,
      'state': 'completed',
      'can_cancel': false,
      'terminal_event_ref': _event,
      'result_sha256': resultSha256,
    };

String _sse(Map<String, Object?> snapshot, OperationResult result) =>
    'id: 1\r\n'
    'event: terminal\r\n'
    'data: ${jsonEncode({'snapshot': snapshot, 'result': result.toJson()})}\r\n'
    '\r\n'
    'id: 2\r\n'
    'event: terminal\r\n'
    'data: [DONE]\r\n'
    '\r\n';
