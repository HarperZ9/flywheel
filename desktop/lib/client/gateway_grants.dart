import 'dart:convert';

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
  'STORE_BUSY': ({503}, 'Gateway approval custody is busy'),
  'STORE_COMMIT_FAILED': ({500}, 'Gateway approval custody failed'),
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
      {required String journeyRef, required String eventHead}) async {
    final result = GatewayGrantProposal.fromJson(await _post(
        '/api/gateway-grants/prepare/${operation.action}',
        operation.prepareBody(journeyRef, eventHead)));
    if (result.invalidResponse ||
        result.action != operation.action ||
        result.journeyRef != journeyRef ||
        result.eventHead != eventHead ||
        result.clientRequestId != operation.clientRequestId ||
        result.summary.journeyRef != journeyRef ||
        result.summary.eventHead != eventHead) {
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
          required String journeyRef,
          required String eventHead,
          required String grantRef}) =>
      _post(path, operation.finalBody(journeyRef, eventHead, grantRef));
}
