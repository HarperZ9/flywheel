import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/gateway_grant_models.dart';
import 'package:flywheel_desktop/models/provider_session_models.dart';

const _a = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _sha = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _source = 'op_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _target = 'op_cccccccccccccccccccccccccccccccc';
const _providerBinding = 'psb_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _binding = GatewayJourneyBinding('jrn_$_a', _sha);

void main() {
  test('turn operation mirrors backend destination and network-only scope', () {
    // Break this catches: the grant sheet names an endpoint/model or broader
    // scope while the engine records a provider-session target.
    final operation = ProviderSessionTurnRequest(
      provider: 'codex',
      workspaceRef: 'workspace-main',
      configDigest: _sha,
      providerBindingRef: _providerBinding,
      permissionScope: const {'write': false, 'exec': false},
      input: 'Plan the repair',
      resumePolicy: ProviderSessionResumePolicy.newThread,
      nativeThreadId: 'thread-1',
      clientUserMessageId: 'user-message-1',
      attachmentRefs: const ['data_context.package:abc'],
    ).toGatewayOperation('desktop-provider-1');

    expect(operation.action, providerSessionTurnAction);
    expect(operation.destination,
        const GatewayDestination('provider-session', 'codex:thread-1'));
    expect(operation.tool, providerSessionTurnAction);
    expect(operation.scopes, ['network']);
    expect(operation.dataRefs, isEmpty);
    expect(operation.credentialRefs, isEmpty);
    expect(operation.operation['stream'], true);
    expect(operation.operation['provider'], 'codex');
    expect(operation.operation['provider_binding_ref'], _providerBinding);
    expect(operation.operation['resume_policy'], 'new_thread');
    expect(
        operation.operation['attachment_refs'], ['data_context.package:abc']);
    expect(
        operation.finalBody(_binding, 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'),
        containsPair('provider', 'codex'));
  });

  test('resume and reconcile preserve source operations without input replay',
      () {
    // Break this catches: recovery resends a user turn instead of making the
    // backend reconcile against the recorded source operation.
    final resume = ProviderSessionResumeRequest(
      provider: 'codex',
      workspaceRef: 'workspace-main',
      configDigest: _sha,
      providerBindingRef: _providerBinding,
      sourceOperationRef: _source,
      nativeThreadId: 'thread-1',
      lastProviderEventId: 'event-7',
    ).toGatewayOperation('desktop-provider-2');
    final reconcile = ProviderSessionReconcileRequest(
      provider: 'codex',
      workspaceRef: 'workspace-main',
      configDigest: _sha,
      providerBindingRef: _providerBinding,
      targetOperationRef: _target,
      reason: 'disconnect_after_input',
      nativeThreadId: 'thread-1',
    ).toGatewayOperation('desktop-provider-3');

    expect(resume.action, providerSessionResumeAction);
    expect(resume.operation['source_operation_ref'], _source);
    expect(resume.operation.containsKey('input'), isFalse);
    expect(reconcile.action, providerSessionReconcileAction);
    expect(reconcile.operation['target_operation_ref'], _target);
    expect(reconcile.operation['reason'], 'disconnect_after_input');
    expect(reconcile.operation.containsKey('input'), isFalse);
  });

  test('invalid provider and malformed native ids fail before dispatch', () {
    // Break this catches: the desktop emits an unsupported provider or unsafe
    // provider-native id and waits for the backend to reject it.
    expect(
      () => ProviderSessionTurnRequest(
        provider: 'openai',
        workspaceRef: 'workspace-main',
        configDigest: _sha,
        providerBindingRef: _providerBinding,
        permissionScope: const {},
        input: 'hello',
        resumePolicy: ProviderSessionResumePolicy.newThread,
      ).toGatewayOperation('desktop-provider-4'),
      throwsA(isA<ArgumentError>()),
    );
    expect(
      () => ProviderSessionTurnRequest(
        provider: 'codex',
        workspaceRef: 'workspace-main',
        configDigest: _sha,
        providerBindingRef: _providerBinding,
        permissionScope: const {},
        input: 'hello',
        resumePolicy: ProviderSessionResumePolicy.newThread,
        nativeThreadId: r'C:\Users\secret',
      ).toGatewayOperation('desktop-provider-5'),
      throwsA(isA<ArgumentError>()),
    );
  });

  test('backend-rejected provider session fields fail before grant', () {
    // Break this catches: the desktop proposes a grantable provider-session
    // operation whose exact field set the backend will reject.
    expect(
      () => GatewayOperation.exact(
        action: providerSessionTurnAction,
        clientRequestId: 'desktop-provider-extra',
        operation: const {
          'provider': 'codex',
          'workspace_ref': 'workspace-main',
          'config_digest': _sha,
          'provider_binding_ref': _providerBinding,
          'stream': true,
          'permission_scope': {'mode': 'manual'},
          'input': 'hello',
          'resume_policy': 'new_thread',
          'unexpected_extra': 'safe-text',
        },
      ),
      throwsA(isA<ArgumentError>()),
    );
    expect(
      () => GatewayOperation.exact(
        action: providerSessionTurnAction,
        clientRequestId: 'desktop-provider-wrong-known-field',
        operation: const {
          'provider': 'codex',
          'workspace_ref': 'workspace-main',
          'config_digest': _sha,
          'provider_binding_ref': _providerBinding,
          'stream': true,
          'permission_scope': {'mode': 'manual'},
          'input': 'hello',
          'resume_policy': 'new_thread',
          'target_operation_ref': _target,
        },
      ),
      throwsA(isA<ArgumentError>()),
    );
    expect(
      () => GatewayOperation.exact(
        action: providerSessionTurnAction,
        clientRequestId: 'desktop-provider-invalid-input',
        operation: const {
          'provider': 'codex',
          'workspace_ref': 'workspace-main',
          'config_digest': _sha,
          'provider_binding_ref': _providerBinding,
          'stream': true,
          'permission_scope': {'mode': 'manual'},
          'input': false,
          'resume_policy': 'new_thread',
        },
      ),
      throwsA(isA<ArgumentError>()),
    );
  });

  test('approval response is separate grant action without stream fields', () {
    // Break this catches: a live provider permission response is treated as a
    // progress label or turn payload instead of a grant-bound operation.
    final allow = ProviderSessionApprovalResponseRequest(
      operationRef: _source,
      nativeRequestId: 'approval-1',
      requestIdentity: _sha,
      decision: 'allow',
      clientResponseId: 'response-1',
      updatedInput: const {'decision': 'accept'},
    ).toGatewayOperation('desktop-provider-approval');

    expect(allow.action, providerSessionApprovalRespondAction);
    expect(allow.operation['operation_ref'], _source);
    expect(allow.operation['decision'], 'allow');
    expect(allow.operation.containsKey('stream'), isFalse);
    expect(allow.operation['updated_input'], {'decision': 'accept'});
    expect(
      () => ProviderSessionApprovalResponseRequest(
        operationRef: _source,
        nativeRequestId: 'approval-1',
        requestIdentity: _sha,
        decision: 'deny',
        clientResponseId: 'response-2',
        updatedInput: const {'decision': 'accept'},
      ).toGatewayOperation('desktop-provider-approval-deny'),
      throwsA(isA<ArgumentError>()),
    );
  });

  test('approval lists require exact envelope and operation-bound rows', () {
    // Break this catches: stale or malformed approval polling responses can be
    // displayed for the current operation and later authorized.
    final approval = _approvalJson(operationRef: _source);
    final parsed = ProviderSessionApprovals.fromJson({
      'schema': 'flywheel.provider-session-approvals/v1',
      'operation_ref': _source,
      'pending': [approval],
    });
    expect(parsed.operationRef, _source);
    expect(parsed.pending.single.requestIdentity, _sha);

    expect(
      () => ProviderSessionApprovals.fromJson({
        'schema': 'flywheel.provider-session-approvals/v1',
        'operation_ref': _source,
        'pending': [_approvalJson(operationRef: _target)],
      }),
      throwsA(isA<ArgumentError>()),
    );
    expect(
      () => ProviderSessionApprovals.fromJson({
        'schema': 'flywheel.provider-session-approvals/v1',
        'operation_ref': _source,
        'pending': [approval],
        'extra': true,
      }),
      throwsA(isA<ArgumentError>()),
    );
    expect(
      () => ProviderSessionApprovals.fromJson({
        'schema': 'wrong',
        'operation_ref': _source,
        'pending': [approval],
      }),
      throwsA(isA<ArgumentError>()),
    );
    expect(
      () => ProviderSessionApprovals.fromJson({
        'schema': 'flywheel.provider-session-approvals/v1',
        'operation_ref': _source,
        'pending': [
          {...approval, 'request_identity': 'not-a-sha'}
        ],
      }),
      throwsA(isA<ArgumentError>()),
    );
  });

  test('approval response identity must be a backend request digest', () {
    // Break this catches: desktop forwards a provider request identity that the
    // backend operation contract would reject after grant approval.
    expect(
      () => ProviderSessionApprovalResponseRequest(
        operationRef: _source,
        nativeRequestId: 'approval-1',
        requestIdentity: 'not-a-sha',
        decision: 'allow',
        clientResponseId: 'response-3',
        updatedInput: const {'decision': 'accept'},
      ).toGatewayOperation('desktop-provider-approval-bad-identity'),
      throwsA(isA<ArgumentError>()),
    );
  });
}

Map<String, Object?> _approvalJson({required String operationRef}) => {
      'operation_ref': operationRef,
      'owner_ref': 'owner_$_a',
      'journey_ref': _binding.journeyRef,
      'request_identity': _sha,
      'provider': 'codex',
      'native_request_id': 'native-approval-1',
      'native_session_id': 'session-1',
      'native_thread_id': 'thread-1',
      'native_turn_id': 'turn-1',
      'native_item_id': 'item-1',
      'tool': 'item/commandExecution/requestApproval',
      'payload_sha256': _sha,
      'config_digest': _sha,
      'capability_digest': _sha,
      'state': 'pending',
    };
