import 'dart:convert';

import '../models/journey_models.dart';
import 'gateway_client.dart';

enum _GrantAction { create, append, check, cancel, export }

Map<String, dynamic> _jsonObjectSnapshot(Map<String, dynamic> source) {
  var remaining = 4096;
  Never invalid() => throw ArgumentError('JSON must be bounded and finite');
  Object? visit(Object? value, int depth) => switch (value) {
        _ when depth > 16 || --remaining < 0 => invalid(),
        null => null,
        String() || bool() => value,
        num() when value.isFinite => value,
        List() => List.unmodifiable(value.map((v) => visit(v, depth + 1))),
        Map() when value.keys.every((key) => key is String) =>
          Map<String, dynamic>.unmodifiable({
            for (final entry in value.entries)
              entry.key as String: visit(entry.value, depth + 1),
          }),
        _ => invalid(),
      };
  return visit(source, 0) as Map<String, dynamic>;
}

class GrantIntent {
  final _GrantAction _action;
  final Map<String, dynamic> _body;
  GrantIntent._(this._action, Map<String, dynamic> body)
      : _body = Map.unmodifiable(body);
  GrantIntent._head(this._action, String journeyRef, String expectedEventHead,
      String clientRequestId, Map<String, dynamic> fields)
      : _body = Map.unmodifiable({
          'journey_ref': journeyRef,
          'expected_event_head': expectedEventHead,
          'client_request_id': clientRequestId,
          ...fields,
        });
  factory GrantIntent.create({
    required String goal,
    required String intakeRef,
    required String clientRequestId,
  }) =>
      GrantIntent._(_GrantAction.create, {
        'goal': goal,
        'intake_ref': intakeRef,
        'client_request_id': clientRequestId,
      });
  factory GrantIntent.append({
    required String journeyRef,
    required String expectedEventHead,
    required String clientRequestId,
    required Map<String, dynamic> command,
  }) =>
      GrantIntent._head(_GrantAction.append, journeyRef, expectedEventHead,
          clientRequestId, {'command': _jsonObjectSnapshot(command)});
  factory GrantIntent.check({
    required String journeyRef,
    required String expectedEventHead,
    required String clientRequestId,
    required String claimId,
    required String oracleId,
    required String candidateRef,
    required String contextRef,
  }) =>
      GrantIntent._head(
          _GrantAction.check, journeyRef, expectedEventHead, clientRequestId, {
        'claim_id': claimId,
        'oracle_id': oracleId,
        'candidate_ref': candidateRef,
        'context_ref': contextRef,
      });
  factory GrantIntent.cancel({
    required String journeyRef,
    required String expectedEventHead,
    required String clientRequestId,
    required String operationRef,
  }) =>
      GrantIntent._head(_GrantAction.cancel, journeyRef, expectedEventHead,
          clientRequestId, {'operation_ref': operationRef});
  factory GrantIntent.export({
    required String journeyRef,
    required String expectedEventHead,
    required String clientRequestId,
    required String packetRef,
  }) =>
      GrantIntent._head(_GrantAction.export, journeyRef, expectedEventHead,
          clientRequestId, {'packet_ref': packetRef});
}

class JourneyCreateRequest {
  final String goal, intakeRef, clientRequestId, grantRef;
  const JourneyCreateRequest(
      {required this.goal,
      required this.intakeRef,
      required this.clientRequestId,
      required this.grantRef});
  Map<String, dynamic> toJson() => {
        'goal': goal,
        'intake_ref': intakeRef,
        'client_request_id': clientRequestId,
        'grant_ref': grantRef
      };
}

abstract class _HeadRequest {
  final String journeyRef, expectedEventHead, clientRequestId, grantRef;
  const _HeadRequest(
      {required this.journeyRef,
      required this.expectedEventHead,
      required this.clientRequestId,
      required this.grantRef});
  Map<String, dynamic> get headJson => {
        'journey_ref': journeyRef,
        'expected_event_head': expectedEventHead,
        'client_request_id': clientRequestId,
        'grant_ref': grantRef
      };
}

class JourneyAppendRequest extends _HeadRequest {
  final Map<String, dynamic> command;
  JourneyAppendRequest(
      {required super.journeyRef,
      required super.expectedEventHead,
      required super.clientRequestId,
      required super.grantRef,
      required Map<String, dynamic> command})
      : command = _jsonObjectSnapshot(command);
  Map<String, dynamic> toJson() => {...headJson, 'command': command};
}

class JourneyCheckRequest extends _HeadRequest {
  final String claimId, oracleId, candidateRef, contextRef;
  const JourneyCheckRequest(
      {required super.journeyRef,
      required super.expectedEventHead,
      required super.clientRequestId,
      required super.grantRef,
      required this.claimId,
      required this.oracleId,
      required this.candidateRef,
      required this.contextRef});
  Map<String, dynamic> toJson() => {
        ...headJson,
        'claim_id': claimId,
        'oracle_id': oracleId,
        'candidate_ref': candidateRef,
        'context_ref': contextRef
      };
}

class JourneyCancelRequest extends _HeadRequest {
  final String operationRef;
  const JourneyCancelRequest(
      {required super.journeyRef,
      required super.expectedEventHead,
      required super.clientRequestId,
      required super.grantRef,
      required this.operationRef});
  Map<String, dynamic> toJson() => {...headJson, 'operation_ref': operationRef};
}

class JourneyExportRequest extends _HeadRequest {
  final String packetRef;
  const JourneyExportRequest(
      {required super.journeyRef,
      required super.expectedEventHead,
      required super.clientRequestId,
      required super.grantRef,
      required this.packetRef});
  Map<String, dynamic> toJson() => {...headJson, 'packet_ref': packetRef};
}

abstract interface class JourneyApi {
  Future<GrantProposal> prepareGrant(GrantIntent intent);
  Future<GrantRef> approveGrantOnce(String proposalRef);
  Future<JourneyMutationAck> create(JourneyCreateRequest request);
  Future<List<JourneySummary>> list();
  Future<JourneyProjection> resume(String journeyRef, JourneyLens lens);
  Future<JourneyMutationAck> append(JourneyAppendRequest request);
  Future<JourneyMutationAck> check(JourneyCheckRequest request);
  Future<JourneyCancelResult> cancel(JourneyCancelRequest request);
  Future<JourneyExportResult> export(JourneyExportRequest request);
}

class JourneyApiException implements Exception {
  final JourneyFailure failure;
  JourneyApiException(this.failure);
}

const _fixedErrors = <String, (Set<int>, String)>{
  'AUTH_REQUIRED': ({401}, 'Journey authorization is required'),
  'PERMISSION_REQUIRED': ({403}, 'Journey approval is required'),
  'PERMISSION_DENIED': ({403}, 'Journey operation is not permitted'),
  'APPROVAL_EXPIRED': ({403}, 'Journey approval expired'),
  'JOURNEY_NOT_FOUND': ({404}, 'Journey was not found'),
  'HEAD_CONFLICT': ({409}, 'Journey state changed'),
  'VERSION_MISMATCH': ({409}, 'Journey data version is unavailable'),
  'IDEMPOTENCY_MISMATCH': ({409}, 'Journey request conflicts with prior use'),
  'INVALID_TRANSITION': ({409, 422}, 'Journey transition is unavailable'),
  'STORE_COMMIT_FAILED': ({500}, 'Journey persistence failed'),
  'STORE_BUSY': ({503}, 'Journey persistence is busy'),
  'CANCEL_UNAVAILABLE': ({409}, 'Journey cancellation is unavailable'),
};

JourneyFailure _localFailure([String code = 'INVALID_RESPONSE']) =>
    JourneyFailure(code,
        _fixedErrors[code]?.$2 ?? 'Gateway response was invalid', const []);

JourneyFailure _readFailure(Object? value) {
  final code = GatewayException.fromResponse(200, jsonEncode(value)).errorCode;
  return code != null && _fixedErrors.containsKey(code)
      ? _localFailure(code)
      : _localFailure();
}

JourneyFailure _gatewayFailure(Object error) {
  if (error is GatewayException && error.errorSchema == gatewayErrorSchema) {
    final code = error.errorCode;
    final fixed = _fixedErrors[code];
    if (code != null && fixed?.$1.contains(error.statusCode) == true) {
      return _localFailure(code);
    }
  }
  return _localFailure();
}

class GatewayJourneyApi implements JourneyApi {
  final GatewayClient _client;
  GatewayJourneyApi(this._client);

  Future<Map<String, dynamic>> _post(
      String path, Map<String, dynamic> body) async {
    try {
      if (utf8.encode(jsonEncode(body)).length > 1048576) {
        throw JourneyApiException(_localFailure());
      }
      final result = await _client.postJson(path, body);
      if (result['schema'] == gatewayErrorSchema) {
        throw JourneyApiException(_readFailure(result));
      }
      return result;
    } on JourneyApiException {
      rethrow;
    } on Object catch (error) {
      throw JourneyApiException(_gatewayFailure(error));
    }
  }

  @override
  Future<GrantProposal> prepareGrant(GrantIntent intent) async =>
      GrantProposal.fromJson(await _post(
          '/api/grants/prepare/${intent._action.name}', intent._body));
  @override
  Future<GrantRef> approveGrantOnce(String proposalRef) async =>
      GrantRef.fromJson(await _post(
          '/api/grants/approve-once', {'proposal_ref': proposalRef}));
  @override
  Future<JourneyMutationAck> create(JourneyCreateRequest request) async =>
      JourneyMutationAck.fromJson(
          await _post('/api/journeys/create', request.toJson()));
  @override
  Future<List<JourneySummary>> list() async {
    final parsed =
        JourneyListResult.fromJson(await _post('/api/journeys/list', const {}));
    if (parsed.invalidResponse) throw JourneyApiException(_localFailure());
    return parsed.journeys;
  }

  @override
  Future<JourneyProjection> resume(String journeyRef, JourneyLens lens) async =>
      JourneyProjection.fromJson(await _post('/api/journeys/resume',
          {'journey_ref': journeyRef, 'lens': _lensName(lens)}));
  @override
  Future<JourneyMutationAck> append(JourneyAppendRequest request) async =>
      JourneyMutationAck.fromJson(
          await _post('/api/journeys/append', request.toJson()));
  @override
  Future<JourneyMutationAck> check(JourneyCheckRequest request) async =>
      JourneyMutationAck.fromJson(
          await _post('/api/journeys/check', request.toJson()));
  @override
  Future<JourneyCancelResult> cancel(JourneyCancelRequest request) async =>
      JourneyCancelResult.fromJson(
          await _post('/api/journeys/cancel', request.toJson()));
  @override
  Future<JourneyExportResult> export(JourneyExportRequest request) async =>
      JourneyExportResult.fromJson(
          await _post('/api/journeys/export', request.toJson()));
}

String _lensName(JourneyLens lens) => switch (lens) {
      JourneyLens.rescue => 'Rescue',
      JourneyLens.diagnose => 'Diagnose',
      JourneyLens.verify => 'Verify',
      JourneyLens.invalidResponse => throw JourneyApiException(_localFailure()),
    };
