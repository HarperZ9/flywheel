// agent_gates.dart — the run's grants, visible and the user's: endpoint,
// write, exec, and whether the active file rides along. Split from the
// panel so the panel stays a composer.

import 'package:flutter/material.dart';

import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';

class AgentGates extends StatelessWidget {
  final List<EndpointRow> endpoints;
  final String? endpoint;
  final bool allowWrite;
  final bool allowExec;
  final bool attachContext;
  final ValueChanged<String?> onEndpoint;
  final ValueChanged<bool> onWrite;
  final ValueChanged<bool> onExec;
  final ValueChanged<bool> onAttach;
  const AgentGates(
      {super.key,
      required this.endpoints,
      required this.endpoint,
      required this.allowWrite,
      required this.allowExec,
      required this.attachContext,
      required this.onEndpoint,
      required this.onWrite,
      required this.onExec,
      required this.onAttach});

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
                  child:
                      Text('${e.name}${e.hasCredential ? '' : ' (no key)'}')),
          ],
          onChanged: onEndpoint,
        ),
        _toggle(t, 'write', allowWrite, onWrite),
        _toggle(t, 'exec', allowExec, onExec),
        _toggle(t, 'attach file', attachContext, onAttach),
      ],
    );
  }

  Widget _toggle(
      FwTokens t, String label, bool value, ValueChanged<bool> onChanged) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          height: 28,
          width: 28,
          child: Checkbox(
              value: value,
              onChanged: (v) => onChanged(v ?? false),
              visualDensity: VisualDensity.compact),
        ),
        Text(label, style: fwMono(t, size: 11, color: t.inkMuted)),
      ],
    );
  }
}
