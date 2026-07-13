// agent_view.dart — the Agent view: the gated, witnessed tool loop over ANY
// endpoint in the roster. The harness carries the agentic behavior, so an
// older model generation gets the same loop, gates, ledger, and integrity
// verdict as the newest one. Write and exec are off until granted here.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class AgentView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const AgentView({super.key, required this.client, required this.alive});

  @override
  State<AgentView> createState() => _AgentViewState();
}

class _AgentViewState extends State<AgentView> {
  final _goal = TextEditingController();
  final _testCmd = TextEditingController();
  List<EndpointRow> _endpoints = [];
  String? _endpoint;
  bool _allowWrite = false;
  bool _allowExec = false;
  bool _running = false;
  Map<String, dynamic>? _result;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadEndpoints();
  }

  @override
  void didUpdateWidget(AgentView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _loadEndpoints();
  }

  @override
  void dispose() {
    _goal.dispose();
    _testCmd.dispose();
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
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _run() async {
    final goal = _goal.text.trim();
    if (goal.isEmpty || _endpoint == null || _running) return;
    setState(() {
      _running = true;
      _result = null;
      _error = null;
    });
    try {
      final r = await widget.client.agent(goal, _endpoint!,
          maxSteps: 8, allowWrite: _allowWrite, allowExec: _allowExec);
      if (mounted) setState(() => _result = r);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. The agent loop appears when it runs.',
          command: 'flywheel up');
    }
    final t = context.fw;
    return ViewScroll(
      children: [
        const SectionHeader('Agent', kicker: 'any model, the same loop'),
        const SizedBox(height: FwLayout.s3),
        Text(
          'The loop is the harness, not the model: gated tools, a witnessed '
          'ledger, and an integrity verdict on every run. Pick any endpoint, '
          'any generation; it inherits the whole environment.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: FwLayout.s4),
        HairlineCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                controller: _goal,
                maxLines: 3,
                minLines: 2,
                style: const TextStyle(fontSize: 13.5),
                decoration:
                    const InputDecoration(hintText: 'What should the agent do?'),
              ),
              const SizedBox(height: FwLayout.s3),
              Wrap(
                spacing: FwLayout.s4,
                runSpacing: FwLayout.s2,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  _endpointPicker(t),
                  _gate('write', _allowWrite, (v) => setState(() => _allowWrite = v)),
                  _gate('exec', _allowExec, (v) => setState(() => _allowExec = v)),
                  SizedBox(
                    width: 220,
                    child: TextField(
                      controller: _testCmd,
                      style: fwMono(t, size: 12),
                      decoration: const InputDecoration(
                          hintText: 'test command (optional)'),
                    ),
                  ),
                  FilledButton(
                    onPressed: _running ? null : _run,
                    child: Text(_running ? 'Running…' : 'Run'),
                  ),
                ],
              ),
            ],
          ),
        ),
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull('The run failed: $_error'),
        ],
        if (_result != null) ...[
          const SizedBox(height: FwLayout.s4),
          _resultCard(t, _result!),
        ],
      ],
    );
  }

  Widget _endpointPicker(FwTokens t) {
    return DropdownButton<String>(
      value: _endpoint,
      underline: const SizedBox(),
      style: fwMono(t, size: 12, color: t.inkSoft),
      items: [
        for (final e in _endpoints)
          DropdownMenuItem(
            value: e.name,
            child: Text('${e.name}${e.hasCredential ? '' : ' (no key)'}'),
          ),
      ],
      onChanged: (v) => setState(() => _endpoint = v),
    );
  }

  Widget _gate(String label, bool value, ValueChanged<bool> onChanged) {
    final t = context.fw;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Checkbox(
            value: value,
            onChanged: (v) => onChanged(v ?? false),
            visualDensity: VisualDensity.compact),
        Text('allow $label', style: fwMono(t, size: 11.5, color: t.inkMuted)),
      ],
    );
  }

  Widget _resultCard(FwTokens t, Map<String, dynamic> r) {
    final integrity = r['integrity'];
    final clean = integrity is Map ? integrity['clean'] == true : null;
    final trusted = r['tests_pass_trusted'];
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: FwLayout.s2,
            runSpacing: FwLayout.s2,
            children: [
              VerdictPill('${r['steps'] ?? '?'} steps', status: 'unverifiable'),
              if (r['verified'] == true)
                const VerdictPill('ledger verified', status: 'verified'),
              if (clean != null)
                VerdictPill(clean ? 'integrity clean' : 'integrity flagged',
                    status: clean ? 'verified' : 'drift'),
              if (trusted != null)
                VerdictPill(
                    trusted == true ? 'tests pass, trusted' : 'tests not proven',
                    status: trusted == true ? 'verified' : 'drift'),
            ],
          ),
          const SizedBox(height: FwLayout.s3),
          SelectableText('${r['final'] ?? ''}',
              style: fwMono(t, size: 12.5).copyWith(height: 1.55)),
          if (r['note'] is String && '${r['note']}'.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('${r['note']}'),
          ],
          if (r['checkpoint'] is String &&
              '${r['checkpoint']}'.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s3),
            HashText('ledger', '${r['checkpoint']}', keep: 32),
          ],
        ],
      ),
    );
  }
}
