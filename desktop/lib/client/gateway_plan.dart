import 'dart:convert';

import '../models/plan_run_models.dart';
import 'gateway_client.dart';
import 'gateway_grants.dart';

final class GatewayPlan {
  final GatewayClient _client;
  GatewayPlan(this._client);

  Future<Map<String, dynamic>> _post(
      String path, Map<String, dynamic> body) async {
    try {
      if (utf8.encode(jsonEncode(body)).length > 1048576) {
        throw const GatewayGrantException(
            'INVALID_RESPONSE', 'Gateway response was invalid');
      }
      return await _client.postJson(path, body);
    } on Object catch (error) {
      throw gatewayGrantFailure(error);
    }
  }

  Future<PlanRunBinding> forge(String goal,
      {String? context,
      List<String>? examples,
      List<String>? documentation,
      String? intentSource,
      String? architectureSource}) async {
    if (goal.trim().isEmpty) {
      throw const GatewayGrantException(
          'INVALID_REQUEST', 'Gateway request is invalid');
    }
    try {
      return PlanRunBinding.fromJson(await _post('/api/plan/forge', {
        'goal': goal.trim(),
        if (context != null) 'context': context,
        if (examples != null) 'examples': List<String>.from(examples),
        if (documentation != null)
          'documentation': List<String>.from(documentation),
        if (intentSource != null) 'intent_source': intentSource,
        if (architectureSource != null)
          'architecture_source': architectureSource,
      }));
    } on GatewayGrantException {
      rethrow;
    } on Object {
      throw const GatewayGrantException(
          'INVALID_RESPONSE', 'Gateway response was invalid');
    }
  }

  Future<Map<String, dynamic>> recheck(String prpId,
          {String? intentSource, String? architectureSource}) =>
      _post('/api/plan/forge/recheck', {
        'prp_id': prpId,
        if (intentSource != null) 'intent_source': intentSource,
        if (architectureSource != null)
          'architecture_source': architectureSource,
      });

  Future<PlanRunResult> dispatch(Map<String, dynamic> finalEnvelope) async {
    try {
      final result = PlanRunResult.fromJson(
          await _post('/api/plan/run', Map.from(finalEnvelope)));
      if (!_matchesEnvelope(result, finalEnvelope)) {
        throw const GatewayGrantException(
            'INVALID_RESPONSE', 'Gateway response was invalid');
      }
      return result;
    } on GatewayGrantException {
      rethrow;
    } on Object {
      throw const GatewayGrantException(
          'INVALID_RESPONSE', 'Gateway response was invalid');
    }
  }
}

bool _matchesEnvelope(
    PlanRunResult result, Map<String, dynamic> finalEnvelope) {
  try {
    final operation = Map<String, Object?>.from(finalEnvelope);
    for (final field in const {
      'schema',
      'journey_ref',
      'expected_event_head',
      'client_request_id',
      'grant_ref'
    }) {
      operation.remove(field);
    }
    final receipt = result.receipt;
    return receipt['journey_ref'] == finalEnvelope['journey_ref'] &&
        receipt['expected_event_head'] ==
            finalEnvelope['expected_event_head'] &&
        receipt['client_request_id'] == finalEnvelope['client_request_id'] &&
        receipt['binding'] is Map &&
        canonicalPlanJson(receipt['binding']) ==
            canonicalPlanJson(operation['binding']) &&
        receipt['operation_sha256'] ==
            canonicalPlanSha256(
                {'action': 'plan.run', 'operation': operation}) &&
        receipt['arguments_sha256'] == canonicalPlanSha256(operation) &&
        receipt['grant_ref_sha256'] ==
            canonicalPlanSha256(finalEnvelope['grant_ref']);
  } on Object {
    return false;
  }
}
