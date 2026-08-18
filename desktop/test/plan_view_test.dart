// Plan view: offline it states the fact and names the command that fixes it,
// exactly like every other destination.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flywheel_desktop/services/settings.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/plan_view.dart';
import 'package:flywheel_desktop/widgets/operation_grant_sheet.dart';
import 'package:flywheel_desktop/widgets/plan_run_controls.dart';

const _a = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _binding = GatewayJourneyBinding('jrn_$_a', '$_a$_a');

Map<String, dynamic> _fixture() => jsonDecode(
        File('../tests/fixtures/plan_run_contract_v1.json').readAsStringSync())
    as Map<String, dynamic>;

Map<String, Object?> _proposal(GatewayOperation operation) {
  final shared = <String, Object?>{
    'action': operation.action,
    'journey_ref': _binding.journeyRef,
    'expected_event_head': _binding.eventHead,
    'destination': operation.destination.toJson(),
    'tool': operation.tool,
    'operation_sha256': '$_a$_a',
    'arguments_sha256': '$_a$_a',
    'scopes': operation.scopes,
    'data_refs': operation.dataRefs,
    'credential_refs': operation.credentialRefs,
    'expires_at': '2026-08-16T12:02:00Z',
  };
  return {
    'schema': 'flywheel.gateway-grant-proposal/v1',
    'proposal_ref': 'prp_$_a',
    'planned_grant_ref': 'gnt_$_a',
    ...shared,
    'client_request_id': operation.clientRequestId,
    'summary': {
      'schema': 'flywheel.gateway-grant-summary/v1',
      ...shared,
      'effect': 'one dispatch after approval',
    }
  };
}

typedef _Harness = ({
  Completer<http.Response> prepare,
  GatewayOperationController grants,
  List<String> calls,
  GatewayOperation Function() captured,
});

void main() {
  _offlineTest();
  _goalEditInvalidationTest();
  _truthCopyTest();
}

void _offlineTest() {
  testWidgets('Plan view offline names the command', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: PlanView(
          client: GatewayClient(), alive: false, settings: DesktopSettings()),
    ));
    await tester.pump();
    expect(find.textContaining('flywheel up'), findsOneWidget);
  });
}

void _truthCopyTest() {
  test('Plan run status copy does not claim forged gates executed', () {
    expect(planRunCompletionCopy,
        'Run recorded. This receipt binds the forged contract; it does not say the listed gates ran or passed.');
    expect(planRunDriftCopy,
        'Run blocked: this plan no longer matches its stored forge contract. Review it and forge again.');
  });
}

void _goalEditInvalidationTest() {
  testWidgets('goal edit during prepare invalidates the bound Plan run',
      (tester) async {
    final harness = await _mountPlan(tester);
    final goal = find.byType(TextField);
    await tester.enterText(goal, 'Implement stable sorting.');
    await tester.pump();
    await tester.ensureVisible(find.text('Forge plan'));
    await tester.tap(find.text('Forge plan'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Run as code-change'));
    await tester.tap(find.text('Run as code-change'));
    await tester.pump();
    expect(harness.calls, ['prepare']);

    await tester.enterText(goal, 'Replace it with goal B.');
    await tester.pump();
    harness.prepare.complete(
        http.Response(jsonEncode(_proposal(harness.captured())), 200));
    await tester.pumpAndSettle();

    expect(harness.grants.failure?.code, 'OPERATION_CHANGED');
    expect(harness.grants.failure?.message,
        'Operation changed; approval was not used');
    expect(
        find.text('Operation changed; approval was not used'), findsOneWidget);
    expect(find.text('Replace it with goal B.'), findsOneWidget);
    expect(find.textContaining('# PRP\nImplement stable sorting.'),
        findsOneWidget);
    expect(harness.calls.where((call) => call == 'approve'), isEmpty);
    expect(harness.calls.where((call) => call == 'dispatch'), isEmpty);
    expect(find.text('Approve once'), findsNothing);
  });
}

Future<_Harness> _mountPlan(WidgetTester tester) async {
  final fixture = _fixture();
  final prepare = Completer<http.Response>();
  final calls = <String>[];
  late GatewayOperation captured;
  final client = GatewayClient(
      baseUrl: 'https://plan.invalid',
      httpClient: MockClient((request) async {
        final path = request.url.path;
        if (path == '/api/projects') {
          return http.Response('{"projects":[{"root":"workspace"}]}', 200);
        }
        if (path == '/api/profiles') {
          return http.Response(
              '{"profiles":[{"name":"code","description":"",'
              '"workflow":"code-change","gates":{}}]}',
              200);
        }
        if (path == '/api/endpoints') {
          return http.Response('{"rows":[{"name":"local"}]}', 200);
        }
        if (path == '/api/plan/forge') {
          return http.Response(jsonEncode(fixture['binding']), 200);
        }
        if (path.contains('/prepare/')) {
          calls.add('prepare');
          return prepare.future;
        }
        if (path.endsWith('/approve-once')) calls.add('approve');
        if (path == '/api/plan/run') calls.add('dispatch');
        return http.Response('{}', 500);
      }));
  final grants = GatewayOperationController(GatewayGrantClient(client));
  await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: GatewayOperationScope(
          authorize: (context, operation, current, dispatch) async {
            captured = operation;
            final ready = await grants.prepare(operation,
                binding: _binding,
                currentOperation: current,
                currentBinding: () => _binding);
            if (!context.mounted || !ready) {
              final failure = grants.failure;
              return failure == null
                  ? const GatewayAuthorizationOutcome<Object?>.denied()
                  : GatewayAuthorizationOutcome<Object?>.failure(failure);
            }
            return showOperationGrantSheet<Object?>(context, grants, dispatch);
          },
          child: Scaffold(
              body: PlanView(
                  client: client, alive: true, settings: DesktopSettings())))));
  await tester.pumpAndSettle();
  return (
    prepare: prepare,
    grants: grants,
    calls: calls,
    captured: () => captured,
  );
}
