// agent_gates.dart — the run's grants, visible and the user's: endpoint,
// write, exec, and whether the active file rides along. Split from the
// panel so the panel stays a composer.

import 'package:flutter/material.dart';

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
  final AgentToolProtocol toolProtocol;
  final ValueChanged<String?> onEndpoint;
  final ValueChanged<String> onModel;
  final ValueChanged<AgentToolProtocol> onToolProtocol;
  final Future<Map<String, dynamic>> Function() loadModels;
  final ValueChanged<bool> onWrite;
  final ValueChanged<bool> onExec;
  final ValueChanged<bool> onAttach;
  final EffortLevel effort;
  final ValueChanged<EffortLevel> onEffort;
  final bool effortEnabled;
  const AgentGates({
    super.key,
    required this.endpoints,
    required this.endpoint,
    required this.model,
    required this.allowWrite,
    required this.allowExec,
    required this.attachContext,
    required this.toolProtocol,
    required this.onEndpoint,
    required this.onModel,
    required this.onToolProtocol,
    required this.loadModels,
    required this.onWrite,
    required this.onExec,
    required this.onAttach,
    required this.effort,
    required this.onEffort,
    this.effortEnabled = true,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Wrap(
      spacing: FwLayout.s3,
      runSpacing: FwLayout.s1,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        DropdownButton<String>(
          value: endpoint,
          underline: const SizedBox(),
          style: fwMono(t, size: 11.5, color: t.inkSoft),
          items: [
            for (final e in endpoints)
              DropdownMenuItem(
                value: e.name,
                child: Text('${e.name}${e.hasCredential ? '' : ' (no key)'}'),
              ),
          ],
          onChanged: onEndpoint,
        ),
        if (endpoint != null)
          ModelSelectorButton(
            loadModels: loadModels,
            current: model,
            onSelect: onModel,
            enabled: effortEnabled,
          ),
        _toggle(t, 'write', allowWrite, onWrite),
        _toggle(t, 'exec', allowExec, onExec),
        _toggle(t, 'attach file', attachContext, onAttach),
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
        EffortDial(value: effort, onChanged: onEffort, enabled: effortEnabled),
      ],
    );
  }

  Widget _toggle(
    FwTokens t,
    String label,
    bool value,
    ValueChanged<bool> onChanged,
  ) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          height: 28,
          width: 28,
          child: Checkbox(
            value: value,
            onChanged: (v) => onChanged(v ?? false),
            visualDensity: VisualDensity.compact,
          ),
        ),
        Text(label, style: fwMono(t, size: 11, color: t.inkMuted)),
      ],
    );
  }
}
