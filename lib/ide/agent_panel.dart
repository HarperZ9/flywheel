// agent_panel.dart — the agent docked under the editor, scoped to the open
// workspace. Same gated loop as everywhere else: write and exec are grants
// the user makes here, the run is witnessed, and the integrity verdict is
// shown, not implied. After a run the Code view reloads clean files.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class AgentPanel extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  final String workspaceRoot;
  final String? activeFile;
  final String? selection;
  final VoidCallback onRunStarted;
  final VoidCallback onRunFinished;
  const AgentPanel(
      {super.key,
      required this.client,
      required this.alive,
      required this.workspaceRoot,
      required this.onRunStarted,
      required this.onRunFinished,
      this.activeFile,
      this.selection});

  @override
  State<AgentPanel> createState() => _AgentPanelState();
}

class _AgentPanelState extends State<AgentPanel> {
  final _goal = TextEditingController();
  List<EndpointRow> _endpoints = [];
  String? _endpoint;
  bool _allowWrite = true; // an IDE agent exists to edit; still a visible grant
  bool _allowExec = false;
  bool _attachContext = true;
  bool _running = false;
  Map<String, dynamic>? _result;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadEndpoints();
  }

  @override
  void dispose() {
    _goal.dispose();
    super.dispose();
  }

  Future<void> _loadEndpoints() async {
    if (!widget.alive) return;
    try {
      final rows = await widget.client.endpointRoster();
      if (mounted) {
        setState(() {
          _endpoints = rows;
          _endpoint ??= rows.isNotEmpty ? rows.first.name : null;
        });
      }
    } catch (_) {}
  }

  Future<void> _run() async {
    var goal = _goal.text.trim();
    if (goal.isEmpty || _endpoint == null || _running) return;
    if (_attachContext && widget.activeFile != null) {
      final sel = widget.selection;
      goal = 'Active file: ${widget.activeFile}\n'
          '${sel != null && sel.isNotEmpty ? 'Selected text:\n$sel\n' : ''}'
          '\n$goal';
    }
    widget.onRunStarted();
    setState(() {
      _running = true;
      _result = null;
      _error = null;
    });
    try {
      final r = await widget.client.agent(goal, _endpoint!,
          maxSteps: 10,
          allowWrite: _allowWrite,
          allowExec: _allowExec,
          root: widget.workspaceRoot);
      if (mounted) setState(() => _result = r);
      widget.onRunFinished();
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Container(
      decoration: BoxDecoration(
        color: t.ground2,
        border: Border(top: BorderSide(color: t.line)),
      ),
      padding: const EdgeInsets.all(FwLayout.s3),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Kicker('workspace agent', hot: true),
              const Spacer(),
              if (!widget.alive)
                Text('engine offline',
                    style: fwMono(t, size: 10.5, color: t.drift)),
            ],
          ),
          const SizedBox(height: FwLayout.s2),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: TextField(
                  controller: _goal,
                  maxLines: 2,
                  minLines: 1,
                  enabled: widget.alive,
                  style: const TextStyle(fontSize: 13),
                  decoration: const InputDecoration(
                      hintText: 'Change this workspace…'),
                  onSubmitted: (_) => _run(),
                ),
              ),
              const SizedBox(width: FwLayout.s2),
              FilledButton(
                onPressed: widget.alive && !_running ? _run : null,
                child: Text(_running ? 'Running…' : 'Run'),
              ),
            ],
          ),
          const SizedBox(height: FwLayout.s2),
          Wrap(
            spacing: FwLayout.s3,
            runSpacing: FwLayout.s1,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              DropdownButton<String>(
                value: _endpoint,
                underline: const SizedBox(),
                style: fwMono(t, size: 11.5, color: t.inkSoft),
                items: [
                  for (final e in _endpoints)
                    DropdownMenuItem(
                        value: e.name,
                        child: Text(
                            '${e.name}${e.hasCredential ? '' : ' (no key)'}')),
                ],
                onChanged: (v) => setState(() => _endpoint = v),
              ),
              _toggle('write', _allowWrite, (v) => setState(() => _allowWrite = v)),
              _toggle('exec', _allowExec, (v) => setState(() => _allowExec = v)),
              _toggle('attach file', _attachContext,
                  (v) => setState(() => _attachContext = v)),
            ],
          ),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s2),
            HonestNull('The run failed: $_error'),
          ],
          if (_result != null) ...[
            const SizedBox(height: FwLayout.s2),
            _resultStrip(t, _result!),
          ],
        ],
      ),
    );
  }

  Widget _toggle(String label, bool value, ValueChanged<bool> onChanged) {
    final t = context.fw;
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

  Widget _resultStrip(FwTokens t, Map<String, dynamic> r) {
    final integrity = r['integrity'];
    final clean = integrity is Map ? integrity['clean'] == true : null;
    return Container(
      constraints: const BoxConstraints(maxHeight: 160),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: FwLayout.s2,
              runSpacing: FwLayout.s1,
              children: [
                VerdictPill('${r['steps'] ?? '?'} steps',
                    status: 'unverifiable'),
                if (r['verified'] == true)
                  const VerdictPill('ledger verified', status: 'verified'),
                if (clean != null)
                  VerdictPill(clean ? 'integrity clean' : 'integrity flagged',
                      status: clean ? 'verified' : 'drift'),
              ],
            ),
            const SizedBox(height: FwLayout.s2),
            SelectableText('${r['final'] ?? ''}',
                style: fwMono(t, size: 11.5).copyWith(height: 1.5)),
          ],
        ),
      ),
    );
  }
}
