part of 'provider_session_models.dart';

final class ProviderSessionApprovals {
  final String operationRef;
  final List<ProviderSessionApproval> pending;

  const ProviderSessionApprovals({
    required this.operationRef,
    required this.pending,
  });

  factory ProviderSessionApprovals.fromJson(Map<String, Object?> json) {
    if (!_exactKeys(json, _approvalEnvelopeKeys) ||
        json['schema'] != providerSessionApprovalsSchema) {
      _bad();
    }
    final ref = json['operation_ref'];
    final pending = json['pending'];
    if (ref is! String || pending is! List) _bad();
    final operationRef = _safe(ref, pattern: _operationRef);
    return ProviderSessionApprovals(
      operationRef: operationRef,
      pending: List<ProviderSessionApproval>.unmodifiable(pending.map((item) {
        if (item is! Map) _bad();
        final approval = ProviderSessionApproval.fromJson(
          Map<String, Object?>.from(item),
        );
        if (approval.operationRef != operationRef) _bad();
        return approval;
      })),
    );
  }
}

final class ProviderSessionApproval {
  final String operationRef, ownerRef, journeyRef, requestIdentity, provider;
  final String nativeRequestId, nativeSessionId, nativeThreadId, nativeTurnId;
  final String nativeItemId, tool, payloadSha256, configDigest;
  final String capabilityDigest, state;

  const ProviderSessionApproval({
    required this.operationRef,
    required this.ownerRef,
    required this.journeyRef,
    required this.requestIdentity,
    required this.provider,
    required this.nativeRequestId,
    required this.nativeSessionId,
    required this.nativeThreadId,
    required this.nativeTurnId,
    required this.nativeItemId,
    required this.tool,
    required this.payloadSha256,
    required this.configDigest,
    required this.capabilityDigest,
    required this.state,
  });

  factory ProviderSessionApproval.fromJson(Map<String, Object?> json) {
    if (!_exactKeys(json, _approvalRowKeys) ||
        json['provider'] is! String ||
        !providerSessionProviders.contains(json['provider']) ||
        json['state'] != 'pending') {
      _bad();
    }
    return ProviderSessionApproval(
      operationRef: _read(json, 'operation_ref', pattern: _operationRef),
      ownerRef: _read(json, 'owner_ref'),
      journeyRef: _read(json, 'journey_ref', pattern: _journeyRef),
      requestIdentity: _read(json, 'request_identity', pattern: sha256Pattern),
      provider: _read(json, 'provider'),
      nativeRequestId: _read(json, 'native_request_id'),
      nativeSessionId: _approvalOptionalText(json, 'native_session_id'),
      nativeThreadId: _approvalOptionalText(json, 'native_thread_id'),
      nativeTurnId: _approvalOptionalText(json, 'native_turn_id'),
      nativeItemId: _approvalOptionalText(json, 'native_item_id'),
      tool: _read(json, 'tool'),
      payloadSha256: _read(json, 'payload_sha256', pattern: sha256Pattern),
      configDigest: _read(json, 'config_digest'),
      capabilityDigest: _approvalOptionalText(json, 'capability_digest'),
      state: _read(json, 'state'),
    );
  }
}

final class ProviderSessionApprovalResponseRequest {
  final String operationRef, nativeRequestId, requestIdentity, decision;
  final String clientResponseId;
  final Map<String, Object?>? updatedInput;

  const ProviderSessionApprovalResponseRequest({
    required this.operationRef,
    required this.nativeRequestId,
    required this.requestIdentity,
    required this.decision,
    required this.clientResponseId,
    this.updatedInput,
  });

  GatewayOperation toGatewayOperation(String requestId) {
    final allow = decision == 'allow';
    if (!allow && decision != 'deny') _bad();
    if (!allow && updatedInput != null) _bad();
    return GatewayOperation.exact(
      action: providerSessionApprovalRespondAction,
      clientRequestId: requestId,
      operation: {
        'operation_ref': _safe(operationRef, pattern: _operationRef),
        'native_request_id': _safe(nativeRequestId),
        'request_identity': _safe(requestIdentity, pattern: sha256Pattern),
        'decision': decision,
        'client_response_id': _safe(clientResponseId),
        if (updatedInput != null) 'updated_input': _json(updatedInput!, 0),
      },
    );
  }
}

const providerSessionApprovalRespondAction =
    'provider.session.approval.respond';
const providerSessionApprovalsPath = '/api/provider-sessions/approvals';
const providerSessionApprovalsRespondPath =
    '/api/provider-sessions/approvals/respond';
const providerSessionApprovalsSchema = 'flywheel.provider-session-approvals/v1';
const _approvalEnvelopeKeys = {'schema', 'operation_ref', 'pending'};
const _approvalRowKeys = {
  'operation_ref',
  'owner_ref',
  'journey_ref',
  'request_identity',
  'provider',
  'native_request_id',
  'native_session_id',
  'native_thread_id',
  'native_turn_id',
  'native_item_id',
  'tool',
  'payload_sha256',
  'config_digest',
  'capability_digest',
  'state',
};

String _approvalOptionalText(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value == null || value == '') return '';
  if (value is String && isSafePublicText(value)) return value;
  _bad();
}
