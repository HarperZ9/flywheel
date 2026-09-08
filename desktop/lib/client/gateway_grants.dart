import 'dart:convert';

import '../models/approval_inbox_models.dart';
import '../models/evidence_state.dart';
import '../models/gateway_grant_models.dart';
import 'gateway_client.dart';

final class GatewayGrantException implements Exception {
  final String code, message;
  const GatewayGrantException(this.code, this.message);
}

const _errors = <String, (Set<int>, String)>{
  'AUTH_REQUIRED': ({401}, 'Gateway authentication is required'),
  'PERMISSION_REQUIRED': ({403}, 'Gateway approval is required'),
  'PERMISSION_DENIED': ({403}, 'Gateway operation is not permitted'),
  'APPROVAL_EXPIRED': ({403}, 'Gateway approval expired'),
  'HEAD_CONFLICT': ({409}, 'Journey state changed'),
  'PLAN_BINDING_DRIFT': ({409}, 'Plan run no longer matches its forge'),
  'IDEMPOTENCY_MISMATCH': (
    {409},
    'Plan run request conflicts with its prior use'
  ),
  'STORE_BUSY': ({503}, 'Gateway approval custody is busy'),
  'STORE_COMMIT_FAILED': ({500}, 'Gateway approval custody failed'),
  'EXTERNAL_ACTION_FAILED': ({502}, 'Authorized external action failed'),
  'INVALID_REQUEST': ({400, 405, 422}, 'Gateway request is invalid'),
  'NOT_FOUND': ({404}, 'Gateway operation was not found'),
};

GatewayGrantException _invalid() => const GatewayGrantException(
    'INVALID_RESPONSE', 'Gateway response was invalid');

GatewayGrantException _failure(Object error) {
  if (error is GatewayException && error.errorSchema == gatewayErrorSchema) {
    final code = error.errorCode;
    final fixed = _errors[code];
    if (code != null && fixed?.$1.contains(error.statusCode) == true) {
      return GatewayGrantException(code, fixed!.$2);
    }
  }
  return _invalid();
}

GatewayGrantException gatewayGrantFailure(Object error) =>
    error is GatewayGrantException ? error : _failure(error);

final class GatewayGrantClient {
  final GatewayClient _client;
  GatewayGrantClient(this._client);

  Future<Map<String, dynamic>> _post(
      String path, Map<String, dynamic> body) async {
    try {
      if (utf8.encode(jsonEncode(body)).length > 1048576) throw _invalid();
      final result = await _client.postJson(path, body);
      if (result['schema'] == gatewayErrorSchema) {
        final structured =
            GatewayException.fromResponse(200, jsonEncode(result));
        final code = structured.errorCode;
        if (code != null && _errors.containsKey(code)) {
          throw GatewayGrantException(code, _errors[code]!.$2);
        }
        throw _invalid();
      }
      return result;
    } on GatewayGrantException {
      rethrow;
    } on Object catch (error) {
      throw _failure(error);
    }
  }

  Future<GatewayGrantProposal> prepare(GatewayOperation operation,
      {required GatewayJourneyBinding binding}) async {
    final result = GatewayGrantProposal.fromJson(await _post(
        '/api/gateway-grants/prepare/${operation.action}',
        operation.prepareBody(binding)));
    if (result.invalidResponse ||
        result.action != operation.action ||
        result.journeyRef != binding.journeyRef ||
        result.eventHead != binding.eventHead ||
        result.clientRequestId != operation.clientRequestId ||
        result.destination != operation.destination ||
        result.tool != operation.tool ||
        !sameGatewayStringList(result.scopes, operation.scopes) ||
        !sameGatewayStringList(result.dataRefs, operation.dataRefs) ||
        !sameGatewayStringList(
            result.credentialRefs, operation.credentialRefs)) {
      throw _invalid();
    }
    return result;
  }

  Future<GatewayGrantCapabilities> capabilities() async {
    final result = GatewayGrantCapabilities.fromJson(Map<String, Object?>.from(
        await _post('/api/gateway-grants/capabilities', const {
      'schema': gatewayGrantCapabilitiesRequestSchema,
    })));
    return result;
  }

  Future<GatewayGrantList> listPending({int limit = 25, String? cursor}) async {
    if (limit < 1 ||
        limit > 50 ||
        cursor != null &&
            (cursor.isEmpty ||
                cursor.length > 256 ||
                !isSafePublicText(cursor))) {
      throw _invalid();
    }
    final result = GatewayGrantList.fromJson(
        Map<String, Object?>.from(await _post('/api/gateway-grants/list', {
      'schema': gatewayGrantListRequestSchema,
      'state': 'pending',
      'limit': limit,
      'cursor': cursor,
    })));
    if (result.invalidResponse) throw _invalid();
    return result;
  }

  Future<GatewayGrantRead> readProposal(String proposalRef) async {
    if (!proposalRefPattern.hasMatch(proposalRef)) throw _invalid();
    final result = GatewayGrantRead.fromJson(
        Map<String, Object?>.from(await _post('/api/gateway-grants/read', {
      'schema': gatewayGrantReadRequestSchema,
      'proposal_ref': proposalRef,
    })));
    if (result.invalidResponse) throw _invalid();
    return result;
  }

  Future<GatewayGrantApproval> approveReviewed(
      String proposalRef, String reviewSha256) async {
    if (!proposalRefPattern.hasMatch(proposalRef) ||
        !sha256Pattern.hasMatch(reviewSha256)) {
      throw _invalid();
    }
    final result = GatewayGrantApproval.fromJson(Map<String, Object?>.from(
        await _post('/api/gateway-grants/approve-reviewed-once', {
      'schema': gatewayGrantApprovalRequestSchema,
      'proposal_ref': proposalRef,
      'review_sha256': reviewSha256,
    })));
    if (result.invalidResponse) throw _invalid();
    return result;
  }

  Future<GatewayGrantRejection> rejectProposal(
      String proposalRef, String recordSha256) async {
    if (!proposalRefPattern.hasMatch(proposalRef) ||
        !sha256Pattern.hasMatch(recordSha256)) {
      throw _invalid();
    }
    final result = GatewayGrantRejection.fromJson(
        Map<String, Object?>.from(await _post('/api/gateway-grants/reject', {
      'schema': gatewayGrantRejectRequestSchema,
      'proposal_ref': proposalRef,
      'expected_record_sha256': recordSha256,
    })));
    if (result.invalidResponse || result.proposalRef != proposalRef) {
      throw _invalid();
    }
    return result;
  }

  Future<GatewayGrantApproval> approve(String proposalRef) async {
    final result = GatewayGrantApproval.fromJson(await _post(
        '/api/gateway-grants/approve-once', {'proposal_ref': proposalRef}));
    if (result.invalidResponse) throw _invalid();
    return result;
  }

  Future<Map<String, dynamic>> dispatch(GatewayOperation operation,
          {required String path,
          required GatewayJourneyBinding binding,
          required String grantRef}) =>
      _post(path, operation.finalBody(binding, grantRef));
}
