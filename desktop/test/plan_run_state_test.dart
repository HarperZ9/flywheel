import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_plan.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/plan_controller.dart';
import 'package:flywheel_desktop/models/plan_run_models.dart';

Map<String, dynamic> _fixture() => jsonDecode(
        File('../tests/fixtures/plan_run_contract_v1.json').readAsStringSync())
    as Map<String, dynamic>;

PlanRunRequest _request(PlanRunBinding binding, {String endpoint = 'local'}) =>
    PlanRunRequest(
        workflow: 'code-change',
        profile: 'code',
        root: r'C:\workspace',
        endpoint: endpoint,
        allowWrite: false,
        allowExec: false,
        binding: binding,
        dataRefs: const [],
        credentialRefs: const [],
        clientRequestId: 'request-1');

PlanController _controller(MockClient transport) => PlanController(GatewayPlan(
    GatewayClient(baseUrl: 'https://gateway.invalid', httpClient: transport)));

void main() {
  _phaseContractTest();
  _forgeFailureTest();
  _denialTest();
  _completionTest();
  _driftTest();
  _invalidResultTest();
  _countersignIdentityTest();
}

void _phaseContractTest() {
  test('controller exposes all eight exact phases', () {
    expect(PlanPhase.values.map((phase) => phase.wireName), [
      'idle',
      'forging',
      'ready',
      'approval_required',
      'running',
      'completed',
      'drift',
      'failed'
    ]);
  });
}

void _forgeFailureTest() {
  test('forge failure keeps goal and last intact binding', () async {
    var fail = false;
    final fixture = _fixture();
    final controller = _controller(MockClient((_) async => fail
        ? http.Response('failed', 500)
        : http.Response(jsonEncode(fixture['binding']), 200)));
    await controller.forge('first');
    final intact = controller.binding;
    fail = true;
    await controller.forge('second');
    expect(controller.goal, 'second');
    expect(controller.binding, same(intact));
    expect(controller.phase, PlanPhase.failed);
  });
}

void _denialTest() {
  test('denial returns ready without running or dispatch', () async {
    final fixture = _fixture();
    final controller = _controller(MockClient(
        (_) async => http.Response(jsonEncode(fixture['binding']), 200)));
    await controller.forge('goal');
    var dispatches = 0;
    await controller.run(_request(controller.binding!),
        currentRequest: () => _request(controller.binding!),
        authorize: (operation, current, dispatch) async =>
            const GatewayAuthorizationOutcome.denied());
    expect(controller.phase, PlanPhase.ready);
    expect(dispatches, 0);
  });
}

void _completionTest() {
  test('running begins only inside final dispatch and completion is verified',
      () async {
    final fixture = _fixture();
    final phases = <PlanPhase>[];
    late PlanController controller;
    final transport = MockClient((request) async {
      if (request.url.path == '/api/plan/forge') {
        return http.Response(jsonEncode(fixture['binding']), 200);
      }
      final result = _result(fixture['binding'] as Map<String, dynamic>);
      return http.Response(jsonEncode(result), 200);
    });
    controller = _controller(transport)
      ..addListener(() => phases.add(controller.phase));
    await controller.forge('goal');
    final request = _request(controller.binding!);
    await controller.run(request,
        currentRequest: () => request,
        authorize: (operation, current, dispatch) async {
          expect(controller.phase, PlanPhase.approvalRequired);
          final value = await dispatch({
            'schema': 'flywheel.gateway-operation/v1',
            'journey_ref': 'jrn_${'a' * 32}',
            'expected_event_head': 'a' * 64,
            'client_request_id': 'request-1',
            'grant_ref': 'gnt_${'a' * 32}',
            ...operation.operation,
          });
          return GatewayAuthorizationOutcome.value(value);
        });
    expect(phases, contains(PlanPhase.running));
    expect(controller.phase, PlanPhase.completed);
    expect(controller.completionMessage,
        'Run recorded. This receipt binds the forged contract; it does not say the listed gates ran or passed.');
  });
}

void _driftTest() {
  test('typed binding drift preserves plan and has exact copy', () async {
    final fixture = _fixture();
    final controller = _controller(MockClient(
        (_) async => http.Response(jsonEncode(fixture['binding']), 200)));
    await controller.forge('goal');
    final binding = controller.binding;
    final request = _request(binding!);
    await controller.run(request,
        currentRequest: () => request,
        authorize: (operation, current, dispatch) async =>
            const GatewayAuthorizationOutcome.failure(
                GatewayOperationFailure('PLAN_BINDING_DRIFT', 'fixed')));
    expect(controller.binding, same(binding));
    expect(controller.phase, PlanPhase.drift);
    expect(controller.failureMessage,
        'Run blocked: this plan no longer matches its stored forge contract. Review it and forge again.');
  });
}

void _invalidResultTest() {
  test('self-consistent result for another request never completes', () async {
    final fixture = _fixture();
    final controller = _controller(MockClient((request) async {
      if (request.url.path == '/api/plan/forge') {
        return http.Response(jsonEncode(fixture['binding']), 200);
      }
      return http.Response(
          jsonEncode(_result(fixture['binding'] as Map<String, dynamic>,
              clientRequestId: 'request-2')),
          200);
    }));
    await controller.forge('goal');
    final request = _request(controller.binding!);
    await controller.run(request,
        currentRequest: () => request,
        authorize: (operation, current, dispatch) async {
          final value = await dispatch({
            'schema': 'flywheel.gateway-operation/v1',
            'journey_ref': 'jrn_${'a' * 32}',
            'expected_event_head': 'a' * 64,
            'client_request_id': 'request-1',
            'grant_ref': 'gnt_${'a' * 32}',
            ...operation.operation,
          });
          return GatewayAuthorizationOutcome.value(value);
        });
    expect(controller.phase, PlanPhase.failed);
    expect(controller.result, isNull);
  });
}

void _countersignIdentityTest() {
  test('rehashed countersign identity drift is refused', () {
    final fixture = _fixture();
    final result = _result(fixture['binding'] as Map<String, dynamic>);
    final workflow = result['workflow_run'] as Map<String, dynamic>;
    (workflow['run_countersign'] as Map<String, dynamic>)['status'] = 'failed';
    final receipt = result['receipt'] as Map<String, dynamic>;
    receipt['workflow_run_sha256'] = canonicalPlanSha256(workflow);
    receipt.remove('receipt_sha256');
    receipt['receipt_sha256'] = canonicalPlanSha256(receipt);
    result.remove('result_sha256');
    result['result_sha256'] = canonicalPlanSha256(result);
    expect(() => PlanRunResult.fromJson(result), throwsFormatException);
  });
}

Map<String, dynamic> _result(Map<String, dynamic> binding,
    {String clientRequestId = 'request-1'}) {
  final operation = {
    'workflow': 'code-change',
    'profile': 'code',
    'root': r'C:\workspace',
    'endpoint': 'local',
    'allow_write': false,
    'allow_exec': false,
    'binding': binding,
    'data_refs': <Object>[],
    'credential_refs': <Object>[]
  };
  final workflow = {
    'schema': 'flywheel.workflow-run/v1',
    'workflow': 'code-change',
    'endpoint': 'local',
    'goal_excerpt': 'goal',
    'started': '2026-08-15T12:00:00',
    'status': 'completed',
    'steps': <Object>[],
    'chain_hash':
        '6f67e6f550d1dfd55933129b0d54878cded9c0aa539a17bdf98442df0b4fc51d',
    'run_countersign': {
      'kind': 'workflow-run',
      'workflow': 'code-change',
      'endpoint': 'local',
      'status': 'completed',
      'chain_hash':
          '6f67e6f550d1dfd55933129b0d54878cded9c0aa539a17bdf98442df0b4fc51d',
      'n_steps': 0,
      'stored': 'ent_1',
      'store_chain_hash': 'b' * 64
    }
  };
  final receipt = {
    'schema': 'flywheel.plan-run-receipt/v2',
    'plan_run_ref': 'plr_${'a' * 32}',
    'binding': binding,
    'journey_ref': 'jrn_${'a' * 32}',
    'expected_event_head': 'a' * 64,
    'client_request_id': clientRequestId,
    'operation_sha256':
        canonicalPlanSha256({'action': 'plan.run', 'operation': operation}),
    'arguments_sha256': canonicalPlanSha256(operation),
    'grant_ref_sha256': canonicalPlanSha256('gnt_${'a' * 32}'),
    'workflow': 'code-change',
    'endpoint': 'local',
    for (final key in [
      'authorization_sha256',
      'execution_plan_sha256',
      'workflow_sha256',
      'profile_sha256',
      'effective_system_sha256'
    ])
      key: 'c' * 64,
    'workflow_run_sha256': canonicalPlanSha256(workflow),
    'workflow_status': 'completed',
    'denominator': {
      'forged_gates': 2,
      'checkable_gates': 2,
      'forged_gates_executed': 0,
      'workflow_steps_recorded': 0
    },
    'does_not_prove': planRunLimitations
  };
  receipt['receipt_sha256'] = canonicalPlanSha256(receipt);
  final result = {
    'schema': 'flywheel.plan-run-result/v2',
    'plan_run_ref': 'plr_${'a' * 32}',
    'receipt': receipt,
    'workflow_run': workflow
  };
  result['result_sha256'] = canonicalPlanSha256(result);
  return result;
}
