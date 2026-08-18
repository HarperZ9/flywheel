import 'package:flutter/material.dart';

import '../models/operation_models.dart';
import '../theme/flywheel_theme.dart';

final class OperationControls extends StatelessWidget {
  final bool alive, authorizing;
  final OperationSnapshot? snapshot;
  final VoidCallback onRun, onStop;
  const OperationControls({
    super.key,
    required this.alive,
    required this.authorizing,
    required this.snapshot,
    required this.onRun,
    required this.onStop,
  });

  @override
  Widget build(BuildContext context) {
    final state = snapshot?.state;
    final stoppable =
        state == OperationState.running && snapshot?.canCancel == true;
    final active = authorizing || (state != null && !state.isTerminal);
    final label = state == OperationState.cancelRequested
        ? 'Stopping…'
        : active
            ? 'Running…'
            : 'Run';
    return Row(mainAxisSize: MainAxisSize.min, children: [
      if (stoppable) ...[
        OutlinedButton.icon(
          key: const ValueKey('operation-stop'),
          onPressed: onStop,
          icon: const Icon(Icons.stop_rounded, size: 16),
          label: const Text('Stop'),
        ),
        const SizedBox(width: FwLayout.s2),
      ],
      FilledButton(
        onPressed: alive && !active ? onRun : null,
        child: Text(label),
      ),
    ]);
  }
}

final class AgentOperationComposer extends StatelessWidget {
  final TextEditingController controller;
  final bool alive, authorizing;
  final OperationSnapshot? snapshot;
  final VoidCallback onRun, onStop;
  const AgentOperationComposer({
    super.key,
    required this.controller,
    required this.alive,
    required this.authorizing,
    required this.snapshot,
    required this.onRun,
    required this.onStop,
  });

  @override
  Widget build(BuildContext context) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: TextField(
              controller: controller,
              maxLines: 2,
              minLines: 1,
              enabled: alive,
              style: const TextStyle(fontSize: 13),
              decoration:
                  const InputDecoration(hintText: 'Change this workspace…'),
              onSubmitted: (_) => onRun(),
            ),
          ),
          const SizedBox(width: FwLayout.s2),
          OperationControls(
              alive: alive,
              authorizing: authorizing,
              snapshot: snapshot,
              onRun: onRun,
              onStop: onStop),
        ],
      );
}
