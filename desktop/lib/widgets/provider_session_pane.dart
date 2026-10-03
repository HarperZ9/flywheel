import 'package:flutter/material.dart';

import '../controllers/provider_session_controller.dart';
import '../models/provider_session_models.dart';

final class ProviderSessionPane extends StatelessWidget {
  final ProviderSessionController controller;
  final VoidCallback? onSendTurn, onStop, onResume, onReconcile;

  const ProviderSessionPane({
    super.key,
    required this.controller,
    this.onSendTurn,
    this.onStop,
    this.onResume,
    this.onReconcile,
  });

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: controller,
        builder: (context, _) {
          final state = controller.state;
          return Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Provider native session',
                  style: Theme.of(context).textTheme.labelLarge,
                ),
                const SizedBox(height: 8),
                Text(_headline(state),
                    style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 16),
                _Fact(label: 'provider', value: state.provider),
                _Fact(label: 'operation', value: state.operationRef),
                _Fact(label: 'session', value: state.nativeSessionId),
                _Fact(label: 'thread', value: state.nativeThreadId),
                _Fact(label: 'turn', value: state.nativeTurnId),
                _Fact(label: 'phase', value: _phaseLabel(state.phase)),
                _Fact(label: 'history', value: state.historyStatus),
                _Fact(label: 'side effect', value: state.sideEffectStatus),
                if (state.needsReconcile) ...[
                  const SizedBox(height: 12),
                  const Text('Reconcile before sending another turn.'),
                ],
                const Spacer(),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    ElevatedButton(
                      onPressed: state.canSendTurn ? onSendTurn : null,
                      child: const Text('Send turn'),
                    ),
                    OutlinedButton(
                      onPressed: state.canStop ? onStop : null,
                      child: const Text('Stop'),
                    ),
                    OutlinedButton(
                      onPressed: state.canResume ? onResume : null,
                      child: const Text('Resume'),
                    ),
                    OutlinedButton(
                      onPressed: state.needsReconcile ? onReconcile : null,
                      child: const Text('Reconcile'),
                    ),
                  ],
                ),
              ],
            ),
          );
        },
      );

  String _headline(ProviderSessionState state) {
    if (state.provider.isEmpty) return 'No provider session selected.';
    if (state.needsReconcile) return 'Session state is uncertain.';
    return 'Session state is inspectable.';
  }
}

final class _Fact extends StatelessWidget {
  final String label, value;
  const _Fact({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    if (value.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Text('$label: $value'),
    );
  }
}

String _phaseLabel(ProviderSessionPhase phase) => switch (phase) {
      ProviderSessionPhase.idle => 'idle',
      ProviderSessionPhase.dispatchIntent => 'dispatch intent',
      ProviderSessionPhase.nativeBinding => 'native binding',
      ProviderSessionPhase.inputSent => 'input sent',
      ProviderSessionPhase.providerEvent => 'provider event',
      ProviderSessionPhase.approvalReplied => 'approval replied',
      ProviderSessionPhase.cancelRequested => 'cancel requested',
      ProviderSessionPhase.cancelAcknowledged => 'cancel acknowledged',
      ProviderSessionPhase.closeIndeterminate => 'close indeterminate',
      ProviderSessionPhase.unknown => 'unknown',
    };
