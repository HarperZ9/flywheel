// plugin_forms.dart — the Plugins view's probe-result readout and the
// register-an-mcp-server form, split out to hold the size gate.

import 'package:flutter/material.dart';

import '../models/tool_spec.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class ProbeResult extends StatelessWidget {
  final Map<String, dynamic> probe;
  final void Function(ToolSpec spec)? onCallTool;
  const ProbeResult({super.key, required this.probe, this.onCallTool});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final status = '${probe['status'] ?? probe['error'] ?? '?'}';
    final specs = ToolSpec.listFromProbe(probe);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            VerdictPill(status,
                status: status == 'live' ? 'verified' : 'drift'),
            if ('${probe['detail'] ?? ''}'.isNotEmpty) ...[
              const SizedBox(width: FwLayout.s2),
              Expanded(
                child: Text('${probe['detail']}',
                    overflow: TextOverflow.ellipsis,
                    style: fwMono(t, size: 10.5, color: t.inkFaint)),
              ),
            ],
          ],
        ),
        if (specs.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          Wrap(
            spacing: 4,
            runSpacing: 4,
            children: [for (final spec in specs) _toolChip(t, spec)],
          ),
        ],
      ],
    );
  }

  Widget _toolChip(FwTokens t, ToolSpec spec) {
    final n = spec.properties.length;
    return InkWell(
      onTap: onCallTool == null ? null : () => onCallTool!(spec),
      borderRadius: BorderRadius.circular(4),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        decoration: BoxDecoration(
          color: t.ground2,
          borderRadius: BorderRadius.circular(4),
          border: Border.all(color: t.hairline),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(spec.name, style: fwMono(t, size: 10)),
            // A faint arg count marks the few tools that take inputs, so a
            // user can tell an actuator from a bare describer at a glance.
            if (n > 0) ...[
              const SizedBox(width: 3),
              Text('$n', style: fwMono(t, size: 9, color: t.inkFaint)),
            ],
          ],
        ),
      ),
    );
  }
}

class RegisterForm extends StatelessWidget {
  final TextEditingController nameController;
  final TextEditingController commandController;
  final VoidCallback onRegister;
  const RegisterForm(
      {super.key,
      required this.nameController,
      required this.commandController,
      required this.onRegister});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              SizedBox(
                width: 160,
                child: TextField(
                  controller: nameController,
                  style: fwMono(t, size: 12.5),
                  decoration: const InputDecoration(hintText: 'name'),
                ),
              ),
              const SizedBox(width: FwLayout.s3),
              Expanded(
                child: TextField(
                  controller: commandController,
                  style: fwMono(t, size: 12.5),
                  decoration: const InputDecoration(
                      hintText: 'command, e.g. gather mcp'),
                  onSubmitted: (_) => onRegister(),
                ),
              ),
              const SizedBox(width: FwLayout.s3),
              FilledButton(onPressed: onRegister, child: const Text('Register')),
            ],
          ),
          const SizedBox(height: FwLayout.s2),
          Text(
              'The command is the argv that starts the server over stdio. '
              'It runs only when probed or when a gated run allows MCP.',
              style: TextStyle(fontSize: 11.5, color: t.inkFaint)),
        ],
      ),
    );
  }
}
