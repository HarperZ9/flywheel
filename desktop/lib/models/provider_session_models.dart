import 'gateway_grant_models.dart';
import 'evidence_state.dart';
import 'operation_models.dart';

part 'provider_session_operations.dart';
part 'provider_session_approvals.dart';
part 'provider_session_state.dart';

final class ProviderSessionBinding {
  final String provider, ownerRef, journeyRef, workspaceRef;
  final String configDigest, capabilityDigest;
  final String providerBindingRef, model, permissionScopeSha256;
  final String reason, runtimeKind, observedAtEventHead;
  final List<String> limitations;
  final bool admitted;

  const ProviderSessionBinding({
    required this.provider,
    required this.ownerRef,
    required this.journeyRef,
    required this.workspaceRef,
    required this.configDigest,
    required this.capabilityDigest,
    required this.providerBindingRef,
    required this.model,
    required this.permissionScopeSha256,
    required this.admitted,
    required this.reason,
    required this.limitations,
    required this.runtimeKind,
    required this.observedAtEventHead,
  });

  factory ProviderSessionBinding.fromJson(Map<String, Object?> json) {
    final provider = json['provider'];
    final owner = json['owner_ref'];
    final journey = json['journey_ref'];
    final workspace = json['workspace_ref'];
    final config = json['config_digest'];
    final capability = json['capability_digest'];
    final ref = json['provider_binding_ref'];
    final model = json['model'];
    final scope = json['permission_scope_sha256'];
    final admitted = json['admitted'];
    final reason = json['reason'];
    final limitations = json['limitations'];
    final runtime = json['runtime_kind'];
    final head = json['observed_at_event_head'];
    if (provider is! String ||
        owner is! String ||
        journey is! String ||
        workspace is! String ||
        config is! String ||
        (capability != null && capability is! String) ||
        ref is! String ||
        (model != null && model is! String) ||
        scope is! String ||
        admitted is! bool ||
        reason is! String ||
        limitations is! List ||
        runtime is! String ||
        head is! String) {
      _bad();
    }
    final capabilityText = capability == null ? '' : capability as String;
    final modelText = model == null ? '' : model as String;
    if (!providerSessionProviders.contains(provider)) _bad();
    return ProviderSessionBinding(
      provider: _safe(provider),
      ownerRef: _safe(owner),
      journeyRef: _safe(journey, pattern: _journeyRef),
      workspaceRef: _safe(workspace),
      configDigest: _safe(config),
      capabilityDigest: capabilityText.isEmpty ? '' : _safe(capabilityText),
      providerBindingRef: _safe(ref, pattern: _providerBindingRef),
      model: modelText.isEmpty ? '' : _safe(modelText),
      permissionScopeSha256: _safe(scope, pattern: sha256Pattern),
      admitted: admitted,
      reason: reason.isEmpty ? '' : _safe(reason),
      limitations: List<String>.unmodifiable(limitations.map((item) {
        if (item is! String || item.isEmpty) _bad();
        return _safe(item);
      })),
      runtimeKind: _safe(runtime),
      observedAtEventHead: _safe(head, pattern: sha256Pattern),
    );
  }
}

final class ProviderSessionBindingRequest {
  final String journeyRef, expectedEventHead, provider, workspaceRef;
  final String? model, toolPolicyRef;
  final Map<String, Object?> permissionScope;

  const ProviderSessionBindingRequest({
    required this.journeyRef,
    required this.expectedEventHead,
    required this.provider,
    required this.workspaceRef,
    required this.permissionScope,
    this.model,
    this.toolPolicyRef,
  });

  Map<String, Object?> toJson() {
    if (!providerSessionProviders.contains(provider)) _bad();
    return {
      'schema': providerSessionBindingRequestSchema,
      'journey_ref': _safe(journeyRef, pattern: _journeyRef),
      'expected_event_head': _safe(expectedEventHead, pattern: sha256Pattern),
      'provider': provider,
      'workspace_ref': _safe(workspaceRef),
      'permission_scope': _json(permissionScope, 0),
      if (_optional(model) case final value?) 'model': value,
      if (_optional(toolPolicyRef) case final value?) 'tool_policy_ref': value,
    };
  }
}

enum ProviderSessionResumePolicy {
  newThread,
  resumeAfterReconcile,
  reconcileBeforeResend;

  String get wire => switch (this) {
        ProviderSessionResumePolicy.newThread => 'new_thread',
        ProviderSessionResumePolicy.resumeAfterReconcile =>
          'resume_after_reconcile',
        ProviderSessionResumePolicy.reconcileBeforeResend =>
          'reconcile_before_resend',
      };
}

enum ProviderSessionPhase {
  idle,
  dispatchIntent,
  nativeBinding,
  inputSent,
  providerEvent,
  approvalReplied,
  cancelRequested,
  cancelAcknowledged,
  closeIndeterminate,
  unknown,
}

const providerSessionTurnAction = 'provider.session.turn';
const providerSessionResumeAction = 'provider.session.resume';
const providerSessionReconcileAction = 'provider.session.reconcile';
const providerSessionTurnPath = '/api/provider-sessions/turn';
const providerSessionResumePath = '/api/provider-sessions/resume';
const providerSessionReconcilePath = '/api/provider-sessions/reconcile';
const providerSessionBindingPath = '/api/provider-sessions/binding';
const providerSessionBindingRequestSchema =
    'flywheel.provider-session-binding-request/v1';
const providerSessionActions = {
  providerSessionTurnAction,
  providerSessionResumeAction,
  providerSessionReconcileAction,
  providerSessionApprovalRespondAction,
};
const providerSessionOperationPaths = {
  providerSessionTurnPath,
  providerSessionResumePath,
  providerSessionReconcilePath,
};

final _operationRef = RegExp(r'^op_[0-9a-f]{32}$');
final _journeyRef = RegExp(r'^jrn_[0-9a-f]{32}$');
final _providerBindingRef = RegExp(r'^psb_[0-9a-f]{32}$');
const providerSessionProviders = {'codex', 'claude'};
const _providers = providerSessionProviders;

Never _bad() => throw ArgumentError('Provider session operation is invalid');

bool _exactKeys(Map<String, Object?> map, Set<String> expected) =>
    map.length == expected.length && map.keys.every(expected.contains);

String _safe(String value, {RegExp? pattern}) {
  if (value.isEmpty || !(pattern?.hasMatch(value) ?? isSafePublicText(value))) {
    _bad();
  }
  return value;
}

String? _optional(String? value, {RegExp? pattern}) =>
    value == null ? null : _safe(value, pattern: pattern);

String _read(Map<String, Object?> map, String key, {RegExp? pattern}) {
  final value = map[key];
  if (value == null) return '';
  if (value is String &&
      value.isNotEmpty &&
      (pattern?.hasMatch(value) ?? isSafePublicText(value))) {
    return value;
  }
  _bad();
}
