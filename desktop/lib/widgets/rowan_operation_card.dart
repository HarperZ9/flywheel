import 'dart:async';

import 'package:flutter/material.dart';

import '../controllers/operation_controller.dart';
import '../controllers/rowan_operation_controller.dart';
import '../models/agent_execution_mode.dart';
import '../models/agent_tool_protocol.dart';
import '../theme/flywheel_theme.dart';
import 'effort_dial.dart';
import 'fw.dart';
import 'model_selector.dart';
import 'operation_controls.dart';
import 'operation_private_attachments.dart';

final class RowanOperationCard extends StatelessWidget {
  const RowanOperationCard({
    super.key,
    required this.rowan,
    required this.root,
    required this.tokens,
    required this.timeout,
    required this.onRun,
  });

  final RowanOperationController rowan;
  final TextEditingController root, tokens, timeout;
  final VoidCallback onRun;

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final snapshot = rowan.snapshot;
    final finalText = rowan.terminalResult?.result['final'];
    final nativeCli = rowan.executionMode.isNativeCli;
    final endpoints = nativeCli
        ? rowan.endpoints
            .where((endpoint) => endpoint.name == 'claude-cli')
            .toList()
        : rowan.endpoints;
    final endpointValue =
        endpoints.any((e) => e.name == rowan.endpoint) ? rowan.endpoint : null;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Kicker('operation review'),
              const Spacer(),
              OperationControls(
                alive: !rowan.recoveryBlocked,
                authorizing: rowan.authorizing,
                snapshot: snapshot,
                onRun: onRun,
                onStop: () => unawaited(rowan.stop(context)),
              ),
            ],
          ),
          const SizedBox(height: FwLayout.s2),
          Wrap(
            spacing: FwLayout.s2,
            runSpacing: FwLayout.s2,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              DropdownButton<AgentExecutionMode>(
                key: const Key('assistant-rowan-execution-mode'),
                value: rowan.executionMode,
                underline: const SizedBox(),
                style: fwMono(t, size: 11.5, color: t.inkSoft),
                items: [
                  for (final value in AgentExecutionMode.values)
                    DropdownMenuItem(value: value, child: Text(value.label)),
                ],
                onChanged: rowan.active || rowan.authorizing
                    ? null
                    : (value) {
                        if (value == null) return;
                        rowan.setExecutionMode(value);
                        if (value.isNativeCli &&
                            !agentExecutionModeSupportsEndpoint(
                                value, rowan.endpoint)) {
                          String? claude;
                          for (final endpoint in rowan.endpoints) {
                            if (endpoint.name == 'claude-cli') {
                              claude = endpoint.name;
                              break;
                            }
                          }
                          rowan.setEndpoint(claude);
                        }
                      },
              ),
              DropdownButton<String>(
                value: endpointValue,
                hint: const Text('endpoint'),
                underline: const SizedBox(),
                style: fwMono(t, size: 11.5, color: t.inkSoft),
                items: [
                  for (final endpoint in endpoints)
                    DropdownMenuItem(
                      value: endpoint.name,
                      child: Text(endpoint.name),
                    ),
                ],
                onChanged: rowan.active || endpoints.isEmpty
                    ? null
                    : rowan.setEndpoint,
              ),
              if (nativeCli)
                Text(
                  'CLI-owned auth; output tokens unsupported; Codex CLI unavailable',
                  style: fwMono(t, size: 10.5, color: t.inkFaint),
                ),
              if (endpointValue != null)
                ModelSelectorButton(
                  enabled: !rowan.active,
                  current: rowan.selectedModel,
                  onSelect: rowan.setModel,
                  loadModels: () => rowan.client.models(rowan.endpoint!),
                ),
              _toggle(
                t,
                'write',
                rowan.allowWrite,
                rowan.active ? null : rowan.setAllowWrite,
              ),
              _toggle(
                t,
                'exec',
                nativeCli ? false : rowan.allowExec,
                rowan.active || nativeCli ? null : rowan.setAllowExec,
              ),
              if (!nativeCli)
                DropdownButton<AgentToolProtocol>(
                  key: const Key('assistant-rowan-tool-protocol'),
                  value: rowan.toolProtocol,
                  underline: const SizedBox(),
                  style: fwMono(t, size: 11.5, color: t.inkSoft),
                  items: [
                    for (final value in AgentToolProtocol.values)
                      DropdownMenuItem(
                        value: value,
                        child: Text(value.label),
                      ),
                  ],
                  onChanged: rowan.active || rowan.authorizing
                      ? null
                      : (value) {
                          if (value != null) rowan.setToolProtocol(value);
                        },
                ),
              if (nativeCli)
                DropdownButton<int>(
                  key: const Key('assistant-rowan-native-cli-max-steps'),
                  value: rowan.maxSteps < 1
                      ? 1
                      : rowan.maxSteps > 12
                          ? 12
                          : rowan.maxSteps,
                  underline: const SizedBox(),
                  style: fwMono(t, size: 11.5, color: t.inkSoft),
                  items: [
                    for (var step = 1; step <= 12; step++)
                      DropdownMenuItem(
                        value: step,
                        child: Text('$step step${step == 1 ? '' : 's'}'),
                      ),
                  ],
                  onChanged: rowan.active || rowan.authorizing
                      ? null
                      : (value) {
                          if (value != null) rowan.setMaxStepsOverride(value);
                        },
                )
              else
                EffortDial(
                  value: rowan.effort,
                  onChanged: rowan.setEffort,
                  enabled: !rowan.active,
                ),
            ],
          ),
          const SizedBox(height: FwLayout.s2),
          _BudgetRow(
            rowan: rowan,
            root: root,
            tokens: tokens,
            timeout: timeout,
          ),
          if (snapshot != null) ...[
            const SizedBox(height: FwLayout.s2),
            Text(
              '${snapshot.operationRef} - ${snapshot.state.name} - seq ${rowan.operationState.lastSequence}',
              style: fwMono(t, size: 10.5, color: t.inkFaint),
              overflow: TextOverflow.ellipsis,
            ),
            OperationPrivateAttachments(
              client: rowan.client,
              snapshot: snapshot,
              result: rowan.terminalResult,
              progress: rowan.progress,
            ),
            if (!snapshot.isTerminal)
              Text(
                'Captions and trace follow accepted private metadata only.',
                style: fwMono(t, size: 10, color: t.inkFaint),
              ),
          ],
          if (rowan.error != null) ...[
            const SizedBox(height: FwLayout.s2),
            HonestNull(rowan.error!),
          ],
          if (rowan.recoveryBlocked) ...[
            const SizedBox(height: FwLayout.s2),
            TextButton(
              onPressed: rowan.dismissRecoveryBlock,
              child: const Text('Dismiss recovery blocker'),
            ),
          ],
          if (snapshot != null &&
              !snapshot.isTerminal &&
              rowan.operationState.observerState !=
                  OperationObserverState.observing) ...[
            const SizedBox(height: FwLayout.s2),
            TextButton.icon(
              onPressed: () => unawaited(rowan.reconnect(snapshot)),
              icon: const Icon(Icons.link_rounded, size: 14),
              label: const Text('Reconnect'),
            ),
          ],
          if (finalText is String && finalText.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s2),
            Text(finalText, style: TextStyle(fontSize: 12, color: t.ink)),
          ],
        ],
      ),
    );
  }

  Widget _toggle(
    FwTokens t,
    String label,
    bool value,
    ValueChanged<bool>? onChanged,
  ) =>
      Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            height: 28,
            width: 28,
            child: Checkbox(
              value: value,
              onChanged:
                  onChanged == null ? null : (v) => onChanged(v ?? false),
              visualDensity: VisualDensity.compact,
            ),
          ),
          Text(label, style: fwMono(t, size: 11, color: t.inkMuted)),
        ],
      );
}

final class _BudgetRow extends StatelessWidget {
  const _BudgetRow({
    required this.rowan,
    required this.root,
    required this.tokens,
    required this.timeout,
  });

  final RowanOperationController rowan;
  final TextEditingController root, tokens, timeout;

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final nativeCli = rowan.executionMode.isNativeCli;
    return Row(
      children: [
        Expanded(
          child: TextField(
            key: const Key('assistant-rowan-root'),
            controller: root,
            enabled: !rowan.active,
            style: fwMono(t, size: 11.5),
            decoration: const InputDecoration(
              isDense: true,
              labelText: 'Gateway workspace root',
            ),
            onChanged: rowan.setWorkspaceRoot,
          ),
        ),
        const SizedBox(width: FwLayout.s2),
        if (nativeCli)
          Text(
            'output tokens unsupported',
            style: fwMono(t, size: 10.5, color: t.inkFaint),
          )
        else
          _NumberField(
            key: const Key('assistant-rowan-max-tokens'),
            controller: tokens,
            enabled: !rowan.active,
            label: 'tokens',
            onSubmitted: rowan.setMaxTokens,
          ),
        const SizedBox(width: FwLayout.s2),
        _NumberField(
          key: const Key('assistant-rowan-timeout'),
          controller: timeout,
          enabled: !rowan.active,
          label: 'seconds',
          onSubmitted: rowan.setTimeoutSeconds,
        ),
      ],
    );
  }
}

final class _NumberField extends StatelessWidget {
  const _NumberField({
    super.key,
    required this.controller,
    required this.enabled,
    required this.label,
    required this.onSubmitted,
  });

  final TextEditingController controller;
  final bool enabled;
  final String label;
  final ValueChanged<int> onSubmitted;

  @override
  Widget build(BuildContext context) => SizedBox(
        width: 96,
        child: TextField(
          controller: controller,
          enabled: enabled,
          keyboardType: TextInputType.number,
          style: fwMono(context.fw, size: 11.5),
          decoration: InputDecoration(isDense: true, labelText: label),
          onSubmitted: (value) {
            final parsed = int.tryParse(value.trim());
            if (parsed != null) onSubmitted(parsed);
          },
        ),
      );
}
