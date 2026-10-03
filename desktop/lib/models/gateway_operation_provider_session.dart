part of 'gateway_grant_models.dart';

const _providerActions = {
  'provider.session.turn',
  'provider.session.resume',
  'provider.session.reconcile',
  'provider.session.approval.respond',
};

bool _isProviderSessionAction(String action) =>
    _providerActions.contains(action);

GatewayDestination _providerDestination(
    String action, Map<String, Object?> value) {
  if (action == 'provider.session.approval.respond') {
    final ref = value['operation_ref'];
    return ref is String && operationRefPattern.hasMatch(ref)
        ? GatewayDestination('provider-approval', ref)
        : _invalid();
  }
  final provider = value['provider'];
  final thread = value['native_thread_id'];
  if (provider is! String || !const {'codex', 'claude'}.contains(provider)) {
    _invalid();
  }
  if (thread != null && (thread is! String || !isSafePublicText(thread))) {
    _invalid();
  }
  return GatewayDestination('provider-session', '$provider:${thread ?? ''}');
}

List<String> _providerScopes() => const ['network'];

void _validateProviderSession(String action, Map<String, Object?> value) {
  _validateProviderFields(action, value);
  if (action == 'provider.session.approval.respond') {
    _validateProviderApprovalResponse(value);
    return;
  }
  final provider = value['provider'];
  final workspace = value['workspace_ref'];
  final digest = value['config_digest'];
  final binding = value['provider_binding_ref'];
  if (provider is! String ||
      !const {'codex', 'claude'}.contains(provider) ||
      workspace is! String ||
      !isSafePublicText(workspace) ||
      digest is! String ||
      !isSafePublicText(digest) ||
      binding is! String ||
      !RegExp(r'^psb_[0-9a-f]{32}$').hasMatch(binding)) {
    _invalid();
  }
  _optionalProviderText(value, 'capability_digest');
  _optionalProviderText(value, 'native_session_id');
  _optionalProviderText(value, 'native_thread_id');
  _optionalProviderText(value, 'native_turn_id');
  _optionalProviderText(value, 'last_provider_event_id');
  _optionalProviderText(value, 'client_user_message_id');
  _optionalProviderText(value, 'tool_policy_ref');
  _optionalProviderText(value, 'source_operation_ref',
      pattern: operationRefPattern);
  _optionalProviderText(value, 'target_operation_ref',
      pattern: operationRefPattern);
  _boundedProviderInt(value, 'timeout_s', 1, 1800);
  _boundedProviderInt(value, 'history_limit', 1, 200);
  final attachments = value['attachment_refs'];
  if (attachments != null &&
      (attachments is! List ||
          attachments
              .any((item) => item is! String || !isSafePublicText(item)))) {
    _invalid();
  }
  if (action == 'provider.session.turn') _validateProviderTurn(value);
  if (action == 'provider.session.resume' &&
      !operationRefPattern.hasMatch('${value['source_operation_ref'] ?? ''}')) {
    _invalid();
  }
  if (action == 'provider.session.reconcile' &&
      (!operationRefPattern
              .hasMatch('${value['target_operation_ref'] ?? ''}') ||
          value['reason'] is! String ||
          !isSafePublicText(value['reason'] as String))) {
    _invalid();
  }
}

void _validateProviderFields(String action, Map<String, Object?> value) {
  const refs = {'data_refs', 'credential_refs'};
  const common = {
    'provider',
    'workspace_ref',
    'config_digest',
    'provider_binding_ref',
    'stream'
  };
  const turnRequired = {
    ...common,
    ...refs,
    'permission_scope',
    'input',
    'resume_policy',
  };
  const turnOptional = {
    'model',
    'native_session_id',
    'native_thread_id',
    'native_turn_id',
    'client_user_message_id',
    'source_operation_ref',
    'timeout_s',
    'attachment_refs',
    'tool_policy_ref',
    'capability_digest',
  };
  const resumeRequired = {...common, ...refs, 'source_operation_ref'};
  const resumeOptional = {
    'native_session_id',
    'native_thread_id',
    'last_provider_event_id',
    'history_limit',
    'capability_digest',
    'timeout_s',
  };
  const reconcileRequired = {
    ...common,
    ...refs,
    'target_operation_ref',
    'reason'
  };
  const reconcileOptional = resumeOptional;
  final required = switch (action) {
    'provider.session.turn' => turnRequired,
    'provider.session.resume' => resumeRequired,
    'provider.session.reconcile' => reconcileRequired,
    'provider.session.approval.respond' => {
        ...refs,
        'operation_ref',
        'native_request_id',
        'request_identity',
        'decision',
        'client_response_id',
      },
    _ => _invalid(),
  };
  final optional = switch (action) {
    'provider.session.turn' => turnOptional,
    'provider.session.resume' => resumeOptional,
    'provider.session.reconcile' => reconcileOptional,
    'provider.session.approval.respond' => {'updated_input'},
    _ => _invalid(),
  };
  final keys = value.keys.toSet();
  if (!keys.containsAll(required) ||
      keys.difference({...required, ...optional}).isNotEmpty ||
      (action != 'provider.session.approval.respond' &&
          value['stream'] != true)) {
    _invalid();
  }
}

void _validateProviderApprovalResponse(Map<String, Object?> value) {
  _optionalProviderText(value, 'operation_ref', pattern: operationRefPattern);
  if (value['operation_ref'] == null) _invalid();
  for (final key in const {
    'native_request_id',
    'request_identity',
    'client_response_id',
  }) {
    _optionalProviderText(value, key);
    if (value[key] == null) _invalid();
  }
  final decision = value['decision'];
  if (decision != 'allow' && decision != 'deny') _invalid();
  final updated = value['updated_input'];
  if (decision == 'deny' && updated != null) _invalid();
  if (decision == 'allow' && updated is! Map) _invalid();
}

void _validateProviderTurn(Map<String, Object?> value) {
  if (!const {
        'new_thread',
        'resume_after_reconcile',
        'reconcile_before_resend',
      }.contains(value['resume_policy']) ||
      value['permission_scope'] is! Map) {
    _invalid();
  }
  final input = value['input'];
  if (input is! String && input is! Map && input is! List) _invalid();
}

void _optionalProviderText(Map<String, Object?> value, String key,
    {RegExp? pattern}) {
  final raw = value[key];
  if (raw == null) return;
  if (raw is String &&
      raw.isNotEmpty &&
      (pattern?.hasMatch(raw) ?? isSafePublicText(raw))) {
    return;
  }
  _invalid();
}

void _boundedProviderInt(
    Map<String, Object?> value, String key, int low, int high) {
  final raw = value[key];
  if (raw == null) return;
  if (raw is int && raw >= low && raw <= high) return;
  _invalid();
}
