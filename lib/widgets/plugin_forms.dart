// plugin_forms.dart — the Plugins view's probe-result readout and the
// register-an-mcp-server form, split out to hold the size gate.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class ProbeResult extends StatelessWidget {
  final Map<String, dynamic> probe;
  const ProbeResult({super.key, required this.probe});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final status = '${probe['status'] ?? probe['error'] ?? '?'}';
    final tools = (probe['tools'] is List)
        ? List<String>.from(probe['tools'])
        : const <String>[];
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
        if (tools.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          Wrap(
            spacing: 4,
            runSpacing: 4,
            children: [
              for (final tool in tools)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: t.ground2,
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: t.hairline),
                  ),
                  child: Text(tool, style: fwMono(t, size: 10)),
                ),
            ],
          ),
        ],
      ],
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
