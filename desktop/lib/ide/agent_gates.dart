// agent_gates.dart — the run's grants, visible and the user's: endpoint,
// write, exec, and whether the active file rides along. Split from the
// panel so the panel stays a composer.

import 'package:flutter/material.dart';

import '../models/agent_execution_mode.dart';
import '../models/agent_tool_protocol.dart';
import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/effort_dial.dart';
import '../widgets/model_selector.dart';

class AgentGates extends StatelessWidget {
  final List<EndpointRow> endpoints;
  final String? endpoint;
  final String? model;
  final bool allowWrite;
  final bool allowExec;
  final bool attachContext;
  final AgentExecutionMode executionMode;
  final AgentToolProtocol toolProtocol;
  final ValueChanged<String?> onEndpoint;
  final ValueChanged<String> onModel;
  final ValueChanged<AgentExecutionMode> onExecutionMode;
  final ValueChanged<AgentToolProtocol> onToolProtocol;
  final Future<Map<String, dynamic>> Function() loadModels;
  final ValueChanged<bool> onWrite;
  final ValueChanged<bool> onExec;
  final ValueChanged<bool> onAttach;
  final EffortLevel effort;
  final ValueChanged<EffortLevel> onEffort;
  final int nativeCliMaxSteps;
  final ValueChanged<int> onNativeCliMaxSteps;
  final bool effortEnabled;
  const AgentGates({
    super.key,
    required this.endpoints,
    required this.endpoint,
    required this.model,
    required this.allowWrite,
    required this.allowExec,
    required this.attachContext,
    required this.executionMode,
    required this.toolProtocol,
    required this.onEndpoint,
    required this.onModel,
    required this.onExecutionMode,
    required this.onToolProtocol,
    required this.loadModels,
    required this.onWrite,
    required this.onExec,
    required this.onAttach,
    required this.effort,
    required this.onEffort,
    required this.nativeCliMaxSteps,
    required this.onNativeCliMaxSteps,
    this.effortEnabled = true,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final nativeCli = executionMode.isNativeCli;
    final visibleEndpoints = nativeCli
        ? endpoints.where((endpoint) => endpoint.name == 'claude-cli').toList()
        : endpoints;
    final endpointValue =
        visibleEndpoints.any((e) => e.name == endpoint) ? endpoint : null;
    return Wrap(
      spacing: FwLayout.s3,
      runSpacing: FwLayout.s1,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        DropdownButton<AgentExecutionMode>(
          key: const Key('agent-execution-mode'),
          value: executionMode,
          underline: const SizedBox(),
          style: fwMono(t, size: 11.5, color: t.inkSoft),
          items: [
            for (final value in AgentExecutionMode.values)
              DropdownMenuItem(value: value, child: Text(value.label)),
          ],
          onChanged: effortEnabled ? (value) => onExecutionMode(value!) : null,
        ),
        DropdownButton<String>(
          value: endpointValue,
          underline: const SizedBox(),
          style: fwMono(t, size: 11.5, color: t.inkSoft),
          items: [
            for (final e in visibleEndpoints)
              DropdownMenuItem(
                value: e.name,
                child: Text('${e.name}${e.hasCredential ? '' : ' (no key)'}'),
              ),
          ],
          onChanged:
              effortEnabled && visibleEndpoints.isNotEmpty ? onEndpoint : null,
        ),
        if (nativeCli)
          Text(
            'CLI-owned auth; output tokens unsupported; Codex CLI unavailable',
            style: fwMono(t, size: 10.5, color: t.inkFaint),
          ),
        if (endpointValue != null)
          ModelSelectorButton(
            loadModels: loadModels,
            current: model,
            onSelect: onModel,
            enabled: effortEnabled,
          ),
        _toggle(t, 'write', allowWrite, onWrite),
        _toggle(
          t,
          'exec',
          nativeCli ? false : allowExec,
          nativeCli ? null : onExec,
        ),
        _toggle(t, 'attach file', attachContext, onAttach),
        if (!nativeCli)
          DropdownButton<AgentToolProtocol>(
            key: const Key('agent-tool-protocol'),
            value: toolProtocol,
            underline: const SizedBox(),
            style: fwMono(t, size: 11.5, color: t.inkSoft),
            items: [
              for (final value in AgentToolProtocol.values)
                DropdownMenuItem(value: value, child: Text(value.label)),
            ],
            onChanged: effortEnabled ? (value) => onToolProtocol(value!) : null,
          ),
        if (nativeCli)
          DropdownButton<int>(
            key: const Key('agent-native-cli-max-steps'),
            value: nativeCliMaxSteps,
            underline: const SizedBox(),
            style: fwMono(t, size: 11.5, color: t.inkSoft),
            items: const [
              DropdownMenuItem(value: 1, child: Text('1 step')),
              DropdownMenuItem(value: 2, child: Text('2 steps')),
              DropdownMenuItem(value: 4, child: Text('4 steps')),
              DropdownMenuItem(value: 8, child: Text('8 steps')),
              DropdownMenuItem(value: 12, child: Text('12 steps')),
            ],
            onChanged: effortEnabled
                ? (value) => onNativeCliMaxSteps(value ?? nativeCliMaxSteps)
                : null,
          )
        else
          EffortDial(
            value: effort,
            onChanged: onEffort,
            enabled: effortEnabled,
          ),
      ],
    );
  }

  Widget _toggle(
    FwTokens t,
    String label,
    bool value,
    ValueChanged<bool>? onChanged,
  ) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          height: 28,
          width: 28,
          child: Checkbox(
            value: value,
            onChanged: onChanged == null ? null : (v) => onChanged(v ?? false),
            visualDensity: VisualDensity.compact,
          ),
        ),
        Text(label, style: fwMono(t, size: 11, color: t.inkMuted)),
      ],
    );
  }
}
