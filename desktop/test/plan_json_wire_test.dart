import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'package:flywheel_desktop/client/gateway_plan.dart';
import 'package:flywheel_desktop/client/strict_plan_json.dart';
import 'package:flywheel_desktop/models/plan_run_models.dart';

Map<String, dynamic> _fixture() => jsonDecode(
        File('../tests/fixtures/plan_run_contract_v1.json').readAsStringSync())
    as Map<String, dynamic>;

Map<String, dynamic> _finalEnvelope() {
  final binding = _fixture()['binding'] as Map<String, dynamic>;
  return {
    'schema': 'flywheel.gateway-operation/v1',
    'journey_ref': 'jrn_${'a' * 32}',
    'expected_event_head': 'a' * 64,
    'client_request_id': 'request-1',
    'grant_ref': 'gnt_${'a' * 32}',
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
}

Map<String, dynamic> _workflow(
    {String workflow = 'code-change', String endpoint = 'local'}) {
  final run = <String, Object?>{
    'schema': 'flywheel.workflow-run/v1',
    'workflow': workflow,
    'endpoint': endpoint,
    'goal_excerpt': 'goal',
    'started': '2026-08-15T12:00:00',
    'steps': <Object>[],
    'status': 'completed',
  };
  final chain = recomputeWorkflowChain(run);
  run['chain_hash'] = chain;
  run['run_countersign'] = {
    'kind': 'workflow-run',
    'workflow': workflow,
    'endpoint': endpoint,
    'status': 'completed',
    'chain_hash': chain,
    'n_steps': 0,
    'stored': 'ent_1',
    'store_chain_hash': 'b' * 64,
  };
  return Map<String, dynamic>.from(run);
}

Map<String, dynamic> _result(
    {String workflow = 'code-change', String endpoint = 'local'}) {
  final envelope = _finalEnvelope();
  final operation = Map<String, Object?>.from(envelope)
    ..remove('schema')
    ..remove('journey_ref')
    ..remove('expected_event_head')
    ..remove('client_request_id')
    ..remove('grant_ref');
  final run = _workflow(workflow: workflow, endpoint: endpoint);
  final receipt = <String, Object?>{
    'schema': 'flywheel.plan-run-receipt/v2',
    'plan_run_ref': 'plr_${'a' * 32}',
    'binding': operation['binding'],
    'journey_ref': envelope['journey_ref'],
    'expected_event_head': envelope['expected_event_head'],
    'client_request_id': envelope['client_request_id'],
    'operation_sha256':
        canonicalPlanSha256({'action': 'plan.run', 'operation': operation}),
    'arguments_sha256': canonicalPlanSha256(operation),
    'authorization_sha256': 'c' * 64,
    'grant_ref_sha256': canonicalPlanSha256(envelope['grant_ref']),
    'execution_plan_sha256': 'd' * 64,
    'workflow': workflow,
    'endpoint': endpoint,
    'workflow_sha256': 'e' * 64,
    'profile_sha256': 'f' * 64,
    'effective_system_sha256': '1' * 64,
    'workflow_run_sha256': canonicalPlanSha256(run),
    'workflow_status': 'completed',
    'denominator': {
      'forged_gates': 2,
      'checkable_gates': 2,
      'forged_gates_executed': 0,
      'workflow_steps_recorded': 0,
    },
    'does_not_prove': planRunLimitations,
  };
  receipt['receipt_sha256'] = canonicalPlanSha256(receipt);
  final result = <String, Object?>{
    'schema': 'flywheel.plan-run-result/v2',
    'plan_run_ref': 'plr_${'a' * 32}',
    'receipt': receipt,
    'workflow_run': run,
  };
  result['result_sha256'] = canonicalPlanSha256(result);
  return Map<String, dynamic>.from(result);
}

Future<void> _expectInvalid(Future<Object?> future) async {
  try {
    await future;
    fail('accepted invalid Plan response');
  } on GatewayGrantException catch (error) {
    expect(error.code, 'INVALID_RESPONSE');
  }
}

void _outerRehash(Map<String, dynamic> result) {
  final run = result['workflow_run'] as Map<String, dynamic>;
  final receipt = result['receipt'] as Map<String, dynamic>;
  receipt['workflow_run_sha256'] = canonicalPlanSha256(run);
  receipt['workflow_status'] = run['status'];
  (receipt['denominator'] as Map<String, dynamic>)['workflow_steps_recorded'] =
      (run['steps'] as List).length;
  receipt.remove('receipt_sha256');
  receipt['receipt_sha256'] = canonicalPlanSha256(receipt);
  result.remove('result_sha256');
  result['result_sha256'] = canonicalPlanSha256(result);
}

Map<String, dynamic> _threeStepResult() {
  final result = _result();
  final run = result['workflow_run'] as Map<String, dynamic>;
  run['steps'] = <Object?>[
    for (final name in ['first', 'middle', 'last'])
      {'name': name, 'kind': 'agent', 'status': 'DONE', 'excerpt': name}
  ];
  run['chain_hash'] = recomputeWorkflowChain(run);
  final sign = run['run_countersign'] as Map<String, dynamic>;
  sign['chain_hash'] = run['chain_hash'];
  sign['n_steps'] = 3;
  _outerRehash(result);
  return result;
}

void main() {
  test('Plan transport rejects decoded duplicate keys before jsonDecode',
      () async {
    final encoded = jsonEncode(_fixture()['binding']);
    final duplicate = encoded.replaceFirst(
        '"schema":"flywheel.prp/v2"',
        '"\\u0073chema":"flywheel.prp/v2",'
            '"schema":"flywheel.prp/v2"');
    final plan = GatewayPlan(GatewayClient(
        baseUrl: 'https://gateway.invalid',
        httpClient: MockClient((_) async => http.Response(duplicate, 200))));
    await _expectInvalid(plan.forge('goal'));
  });

  test('Plan transport rejects duplicate keys at every nested boundary',
      () async {
    final encoded = jsonEncode(_result());
    final mutations = [
      encoded.replaceFirst(
          '{', r'{"\u0073chema":"flywheel.plan-run-result/v2",'),
      encoded.replaceFirst(
          '"receipt":{', '"receipt":{"schema":"flywheel.plan-run-receipt/v2",'),
      encoded.replaceFirst(
          '"workflow_run":{', '"workflow_run":{"endpoint":"local",'),
      encoded.replaceFirst(
          '"binding":{', '"binding":{"schema":"flywheel.plan-run-binding/v1",'),
      encoded.replaceFirst('"prp":{', '"prp":{"schema":"flywheel.prp/v2",'),
      encoded.replaceFirst('"gates":[{', '"gates":[{"check":"duplicate",'),
      encoded.replaceFirst(
          '"steps":[]', r'"steps":[{"name":"x","\u006eame":"x"}]'),
    ];
    for (final raw in mutations) {
      final plan = GatewayPlan(GatewayClient(
          baseUrl: 'https://gateway.invalid',
          httpClient: MockClient((_) async => http.Response(raw, 200))));
      await _expectInvalid(plan.dispatch(_finalEnvelope()));
    }
  });

  test('strict Plan JSON rejects surrogate positions and admits pairs', () {
    final invalid = [
      r'{"value":"\uD800leading"}',
      r'{"value":"trailing\uD800"}',
      r'{"value":"\uDC00"}',
      r'{"nested":["ok","\uDFFF"]}',
      r'{"\uD800":"key"}',
      r'{"key":{"\uDC00":"nested"}}',
    ];
    for (final raw in invalid) {
      expect(
          () => strictPlanJsonObject(utf8.encode(raw)), throwsFormatException);
    }
    expect(strictPlanJsonObject(utf8.encode(r'{"value":"\uD83D\uDE00"}')), {
      'value': String.fromCharCodes([0xd83d, 0xde00])
    });
  });

  test('shared Unicode fixture reproduces the exact Python workflow chain', () {
    final fixture = jsonDecode(
        File('../tests/fixtures/plan_workflow_chain_v1.json')
            .readAsStringSync()) as Map<String, dynamic>;
    final run = Map<String, Object?>.from(fixture['workflow_run'] as Map);
    expect(recomputeWorkflowChain(run), fixture['chain_hash']);
  });

  test('Plan transport rejects invalid UTF-8 trailing scalar depth and nodes',
      () async {
    final responses = <http.Response>[
      http.Response.bytes([0xff], 200),
      http.Response('{}{}', 200),
      http.Response('[]', 200),
      http.Response(r'{"x":01}', 200),
      http.Response(r'{"x":tru}', 200),
      http.Response(r'{"x":"\q"}', 200),
      http.Response('${'[' * 18}0${']' * 18}', 200),
      http.Response(jsonEncode({for (var i = 0; i < 4100; i++) '$i': i}), 200),
      http.Response(' ' * 1048577, 200),
    ];
    for (final response in responses) {
      final plan = GatewayPlan(GatewayClient(
          baseUrl: 'https://gateway.invalid',
          httpClient: MockClient((_) async => response)));
      await _expectInvalid(plan.forge('goal'));
    }
  });

  test('outer rehash cannot hide nested chain or countersign drift', () {
    final mutations = <void Function(Map<String, dynamic>)>[
      (run) => run['workflow'] = 'research-brief',
      (run) => run['endpoint'] = 'remote-other',
      (run) => run['goal_excerpt'] = 'changed',
      (run) => run['started'] = '2026-08-15T12:00:01',
      (run) => (run['steps'] as List)[0]['excerpt'] = 'changed',
      (run) => (run['steps'] as List)[1]['excerpt'] = 'changed',
      (run) => (run['steps'] as List)[2]['excerpt'] = 'changed',
      (run) =>
          (run['steps'] as List).setAll(0, (run['steps'] as List).reversed),
      (run) => (run['steps'] as List).insert(1, {'duplicate': true}),
      (run) => (run['steps'] as List).removeAt(1),
      (run) => (run['steps'] as List).add((run['steps'] as List).last),
      (run) => run['status'] = 'FAILED',
      (run) => run['chain_hash'] = '0' * 64,
      (run) => (run['run_countersign'] as Map)['status'] = 'FAILED',
    ];
    for (final mutate in mutations) {
      final result = _threeStepResult();
      mutate(result['workflow_run'] as Map<String, dynamic>);
      _outerRehash(result);
      expect(() => PlanRunResult.fromJson(result), throwsFormatException);
    }
  });

  test('v1 missing unknown and null result fields fail closed', () async {
    final mutations = <void Function(Map<String, dynamic>)>[
      (value) => value['schema'] = 'flywheel.plan-run-result/v1',
      (value) =>
          (value['receipt'] as Map)['schema'] = 'flywheel.plan-run-receipt/v1',
      (value) => (value['receipt'] as Map).remove('workflow'),
      (value) => (value['receipt'] as Map)['unknown'] = null,
      (value) => (value['receipt'] as Map)['endpoint'] = null,
    ];
    for (final mutate in mutations) {
      final result = _result();
      mutate(result);
      _outerRehash(result);
      expect(() => PlanRunResult.fromJson(result), throwsFormatException);
    }
    final legacy = _result()..['schema'] = 'flywheel.plan-run-result/v1';
    _outerRehash(legacy);
    final plan = GatewayPlan(GatewayClient(
        baseUrl: 'https://gateway.invalid',
        httpClient:
            MockClient((_) async => http.Response(jsonEncode(legacy), 200))));
    await _expectInvalid(plan.dispatch(_finalEnvelope()));
  });

  for (final identity in const [
    ('research-brief', 'local'),
    ('code-change', 'remote-other'),
  ]) {
    test('self-consistent wrong ${identity.$1}|${identity.$2} is refused',
        () async {
      final result = _result(workflow: identity.$1, endpoint: identity.$2);
      final plan = GatewayPlan(GatewayClient(
          baseUrl: 'https://gateway.invalid',
          httpClient:
              MockClient((_) async => http.Response(jsonEncode(result), 200))));
      await _expectInvalid(plan.dispatch(_finalEnvelope()));
    });
  }
}
