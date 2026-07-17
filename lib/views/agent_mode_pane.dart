// agent_mode_pane.dart — the tool loop inside the Chat destination: pick
// a workspace root, then drive the same gated, witnessed agent the Code
// lane uses (write and exec are grants, never defaults; every run
// persists with its trace). The audit's sharpest finding was that the
// destination named for the agent never ran it; this pane closes that.

import 'dart:io';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../ide/agent_panel.dart';
import '../services/settings.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class AgentModePane extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  final DesktopSettings settings;
  const AgentModePane(
      {super.key,
      required this.client,
      required this.alive,
      required this.settings});

  @override
  State<AgentModePane> createState() => _AgentModePaneState();
}

class _AgentModePaneState extends State<AgentModePane> {
  String? _root;
  final _rootField = TextEditingController();

  @override
  void dispose() {
    _rootField.dispose();
    super.dispose();
  }

  void _use(String path) {
    final dir = path.trim();
    if (dir.isEmpty) return;
    if (!Directory(dir).existsSync()) {
      setState(() => _root = null);
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('No such folder: $dir')));
      return;
    }
    widget.settings.rememberWorkspace(dir);
    setState(() => _root = dir);
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final root = _root;
    if (root == null) return _picker(t);
    return Column(children: [
      Container(
        padding: const EdgeInsets.symmetric(
            horizontal: FwLayout.s5, vertical: FwLayout.s2),
        decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: t.hairline))),
        child: Row(children: [
          Text('root', style: fwMono(t, size: 11, color: t.inkFaint)),
          const SizedBox(width: FwLayout.s2),
          Expanded(
            child: Text(root,
                style: fwMono(t, size: 11.5).copyWith(color: t.inkMuted),
                overflow: TextOverflow.ellipsis),
          ),
          TextButton(
            onPressed: () => setState(() => _root = null),
            child: const Text('change'),
          ),
        ]),
      ),
      Expanded(
        child: AgentPanel(
          client: widget.client,
          alive: widget.alive,
          workspaceRoot: root,
          onRunStarted: () {},
          onRunFinished: () {},
        ),
      ),
    ]);
  }

  Widget _picker(FwTokens t) {
    final recents = widget.settings.recentWorkspaces;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 560),
        child: HairlineCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('Point the agent at a workspace',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: FwLayout.s2),
              Text(
                  'The tool loop runs inside one folder. Reads are free; '
                  'writes and shell commands are grants you switch on per '
                  'run, and every run persists with its full trace.',
                  style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
              const SizedBox(height: FwLayout.s3),
              Row(children: [
                Expanded(
                  child: TextField(
                    controller: _rootField,
                    style: fwMono(t, size: 12.5),
                    onSubmitted: _use,
                    decoration: const InputDecoration(
                        hintText: r'a folder, e.g. C:\dev\my-project'),
                  ),
                ),
                const SizedBox(width: FwLayout.s3),
                FilledButton(
                  onPressed: () => _use(_rootField.text),
                  child: const Text('Use it'),
                ),
              ]),
              if (recents.isNotEmpty) ...[
                const SizedBox(height: FwLayout.s3),
                Text('recent', style: fwMono(t, size: 10.5, color: t.inkFaint)),
                const SizedBox(height: FwLayout.s1),
                for (final r in recents.take(5))
                  InkWell(
                    onTap: () => _use(r),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 3),
                      child: Text(r,
                          style: fwMono(t, size: 11.5)
                              .copyWith(color: t.drift),
                          overflow: TextOverflow.ellipsis),
                    ),
                  ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
