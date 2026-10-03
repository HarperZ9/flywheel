import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/controllers/provider_session_controller.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/models/provider_session_models.dart';

const _sha = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _opA = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _opB = 'op_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

void main() {
  test('controller folds provider progress into inspectable session state', () {
    // Break this catches: provider-native ids arrive in progress but never show
    // in the desktop state a user can inspect.
    final controller = ProviderSessionController()..begin(_opA);
    addTearDown(controller.dispose);

    controller.acceptProgress({
      'provider_session': {
        'phase': 'native_binding',
        'provider': 'codex',
        'operation_ref': _opA,
        'native_session_id': 'session-1',
        'native_thread_id': 'thread-1',
        'config_digest': _sha,
      },
    });

    expect(controller.state.provider, 'codex');
    expect(controller.state.phase, ProviderSessionPhase.nativeBinding);
    expect(controller.state.nativeThreadId, 'thread-1');
    expect(controller.state.canStop, isTrue);
    expect(controller.state.needsReconcile, isFalse);
  });

  test('stale provider progress cannot overwrite the active operation', () {
    // Break this catches: a late event from an old provider operation changes
    // the visible session ids for the operation the user is actually viewing.
    final controller = ProviderSessionController()..begin(_opA);
    addTearDown(controller.dispose);
    controller.acceptProgress({
      'provider_session': {
        'phase': 'native_binding',
        'provider': 'codex',
        'operation_ref': _opA,
        'native_thread_id': 'thread-a',
      },
    });
    controller.acceptProgress({
      'provider_session': {
        'phase': 'native_binding',
        'provider': 'claude',
        'operation_ref': _opB,
        'native_thread_id': 'thread-b',
      },
    });

    expect(controller.state.provider, 'codex');
    expect(controller.state.nativeThreadId, 'thread-a');
  });

  test('indeterminate terminal result requires reconciliation before resend',
      () {
    // Break this catches: an uncertain provider write looks complete enough for
    // the UI to invite another send instead of requiring reconciliation.
    final controller = ProviderSessionController()..begin(_opA);
    addTearDown(controller.dispose);
    controller.acceptTerminal(OperationResult.fromJson({
      'schema': operationResultSchema,
      'operation_ref': _opA,
      'action': providerSessionTurnAction,
      'state': 'failed',
      'result': {
        'reason': 'AGENT_NATIVE_INCOMPLETE',
        'provider_session': {
          'provider': 'codex',
          'native_thread_id': 'thread-1',
          'config_digest': _sha,
        },
        'history_status': 'indeterminate',
        'side_effect_status': 'unknown_after_send',
      },
    }));

    expect(controller.state.needsReconcile, isTrue);
    expect(controller.state.canResume, isTrue);
    expect(controller.state.canSendTurn, isFalse);
  });

  test('malformed terminal result remains reconcile required', () {
    // Break this catches: a provider terminal result with no provider_session
    // or side-effect status becomes a terminal, healthy, sendable UI state.
    final controller = ProviderSessionController()..begin(_opA);
    addTearDown(controller.dispose);
    controller.acceptTerminal(OperationResult.fromJson(const {
      'schema': operationResultSchema,
      'operation_ref': _opA,
      'action': providerSessionTurnAction,
      'state': 'completed',
      'result': {},
    }));

    expect(controller.state.terminal, isTrue);
    expect(controller.state.reason, 'AGENT_NATIVE_INCOMPLETE');
    expect(controller.state.historyStatus, 'indeterminate');
    expect(controller.state.sideEffectStatus, 'indeterminate');
    expect(controller.state.needsReconcile, isTrue);
    expect(controller.state.canSendTurn, isFalse);
  });
}
