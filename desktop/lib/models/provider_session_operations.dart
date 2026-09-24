part of 'provider_session_models.dart';

Object? _json(Object? value, int depth) {
  if (depth > 12) _bad();
  if (value == null || value is bool || value is int) return value;
  if (value is num) return value.isFinite ? value : _bad();
  if (value is String) return _safe(value);
  if (value is List) {
    return List<Object?>.unmodifiable(
        value.map((item) => _json(item, depth + 1)));
  }
  if (value is Map && value.keys.every((key) => key is String)) {
    return Map<String, Object?>.unmodifiable({
      for (final entry in value.entries)
        entry.key as String: _json(entry.value, depth + 1),
    });
  }
  return _bad();
}

Map<String, Object?> _common({
  required String provider,
  required String workspaceRef,
  required String configDigest,
  required String providerBindingRef,
  String? nativeSessionId,
  String? nativeThreadId,
  String? capabilityDigest,
  int? timeoutSeconds,
}) {
  if (!_providers.contains(provider)) _bad();
  final result = <String, Object?>{
    'provider': provider,
    'workspace_ref': _safe(workspaceRef),
    'config_digest': _safe(configDigest),
    'provider_binding_ref':
        _safe(providerBindingRef, pattern: _providerBindingRef),
    'stream': true,
    if (_optional(nativeSessionId) case final value?)
      'native_session_id': value,
    if (_optional(nativeThreadId) case final value?) 'native_thread_id': value,
    if (_optional(capabilityDigest) case final value?)
      'capability_digest': value,
  };
  if (timeoutSeconds != null) {
    if (timeoutSeconds < 1 || timeoutSeconds > 1800) _bad();
    result['timeout_s'] = timeoutSeconds;
  }
  return result;
}

final class ProviderSessionTurnRequest {
  final String provider, workspaceRef, configDigest, providerBindingRef;
  final String? model, nativeSessionId, nativeThreadId, nativeTurnId;
  final String? clientUserMessageId, sourceOperationRef, toolPolicyRef;
  final String? capabilityDigest;
  final int? timeoutSeconds;
  final Map<String, Object?> permissionScope;
  final Object input;
  final ProviderSessionResumePolicy resumePolicy;
  final List<String> attachmentRefs;

  const ProviderSessionTurnRequest({
    required this.provider,
    required this.workspaceRef,
    required this.configDigest,
    required this.providerBindingRef,
    required this.permissionScope,
    required this.input,
    required this.resumePolicy,
    this.model,
    this.nativeSessionId,
    this.nativeThreadId,
    this.nativeTurnId,
    this.clientUserMessageId,
    this.sourceOperationRef,
    this.timeoutSeconds,
    this.attachmentRefs = const [],
    this.toolPolicyRef,
    this.capabilityDigest,
  });

  GatewayOperation toGatewayOperation(String requestId) =>
      GatewayOperation.exact(
        action: providerSessionTurnAction,
        clientRequestId: requestId,
        operation: {
          ..._common(
            provider: provider,
            workspaceRef: workspaceRef,
            configDigest: configDigest,
            providerBindingRef: providerBindingRef,
            nativeSessionId: nativeSessionId,
            nativeThreadId: nativeThreadId,
            capabilityDigest: capabilityDigest,
            timeoutSeconds: timeoutSeconds,
          ),
          'permission_scope': _json(permissionScope, 0),
          'input': _json(input, 0),
          'resume_policy': resumePolicy.wire,
          if (_optional(model) case final value?) 'model': value,
          if (_optional(nativeTurnId) case final value?)
            'native_turn_id': value,
          if (_optional(clientUserMessageId) case final value?)
            'client_user_message_id': value,
          if (_optional(sourceOperationRef, pattern: _operationRef)
              case final value?)
            'source_operation_ref': value,
          if (attachmentRefs.isNotEmpty)
            'attachment_refs':
                List<String>.unmodifiable(attachmentRefs.map(_safe)),
          if (_optional(toolPolicyRef) case final value?)
            'tool_policy_ref': value,
        },
      );
}

final class ProviderSessionResumeRequest {
  final String provider, workspaceRef, configDigest, providerBindingRef;
  final String sourceOperationRef;
  final String? nativeSessionId, nativeThreadId, lastProviderEventId;
  final String? capabilityDigest;
  final int? historyLimit, timeoutSeconds;

  const ProviderSessionResumeRequest({
    required this.provider,
    required this.workspaceRef,
    required this.configDigest,
    required this.providerBindingRef,
    required this.sourceOperationRef,
    this.nativeSessionId,
    this.nativeThreadId,
    this.lastProviderEventId,
    this.historyLimit,
    this.capabilityDigest,
    this.timeoutSeconds,
  });

  GatewayOperation toGatewayOperation(String requestId) =>
      GatewayOperation.exact(
        action: providerSessionResumeAction,
        clientRequestId: requestId,
        operation: {
          ..._common(
            provider: provider,
            workspaceRef: workspaceRef,
            configDigest: configDigest,
            providerBindingRef: providerBindingRef,
            nativeSessionId: nativeSessionId,
            nativeThreadId: nativeThreadId,
            capabilityDigest: capabilityDigest,
            timeoutSeconds: timeoutSeconds,
          ),
          'source_operation_ref':
              _safe(sourceOperationRef, pattern: _operationRef),
          if (_optional(lastProviderEventId) case final value?)
            'last_provider_event_id': value,
          if (historyLimit != null) 'history_limit': historyLimit,
        },
      );
}

final class ProviderSessionReconcileRequest {
  final String provider, workspaceRef, configDigest, providerBindingRef;
  final String targetOperationRef, reason;
  final String? nativeSessionId, nativeThreadId, lastProviderEventId;
  final String? capabilityDigest;
  final int? historyLimit, timeoutSeconds;

  const ProviderSessionReconcileRequest({
    required this.provider,
    required this.workspaceRef,
    required this.configDigest,
    required this.providerBindingRef,
    required this.targetOperationRef,
    required this.reason,
    this.nativeSessionId,
    this.nativeThreadId,
    this.lastProviderEventId,
    this.historyLimit,
    this.capabilityDigest,
    this.timeoutSeconds,
  });

  GatewayOperation toGatewayOperation(String requestId) =>
      GatewayOperation.exact(
        action: providerSessionReconcileAction,
        clientRequestId: requestId,
        operation: {
          ..._common(
            provider: provider,
            workspaceRef: workspaceRef,
            configDigest: configDigest,
            providerBindingRef: providerBindingRef,
            nativeSessionId: nativeSessionId,
            nativeThreadId: nativeThreadId,
            capabilityDigest: capabilityDigest,
            timeoutSeconds: timeoutSeconds,
          ),
          'target_operation_ref':
              _safe(targetOperationRef, pattern: _operationRef),
          'reason': _safe(reason),
          if (_optional(lastProviderEventId) case final value?)
            'last_provider_event_id': value,
          if (historyLimit != null) 'history_limit': historyLimit,
        },
      );
}
