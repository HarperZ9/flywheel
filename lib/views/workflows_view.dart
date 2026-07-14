// workflows_view.dart — staged runs over any endpoint, shaped by a profile
// manifest. Every step carries its own verdict and the whole run carries one
// chained receipt. A verify step without an exec grant says UNVERIFIABLE;
// nothing here dresses up an unproven result.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../models/workflow_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import '../widgets/workflow_cards.dart';

class WorkflowsView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const WorkflowsView({super.key, required this.client, required this.alive});

  @override
  State<WorkflowsView> createState() => _WorkflowsViewState();
}

class _WorkflowsViewState extends State<WorkflowsView> {
  final _goal = TextEditingController();
  List<ProfileManifest> _profiles = [];
  WorkflowRoster? _roster;
  List<EndpointRow> _endpoints = [];
  String? _profile;
  String? _workflow;
  String? _endpoint;
  bool _allowWrite = false;
  bool _allowExec = false;
  bool _running = false;
  WorkflowRun? _run;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(WorkflowsView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  @override
  void dispose() {
    _goal.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (!widget.alive) return;
    try {
      final results = await Future.wait([
        widget.client.profiles(),
        widget.client.workflows(),
        widget.client.endpointRoster(),
      ]);
      if (mounted) {
        setState(() {
          _profiles = results[0] as List<ProfileManifest>;
          _roster = results[1] as WorkflowRoster;
          _endpoints = results[2] as List<EndpointRow>;
          _profile ??= _profiles.isNotEmpty ? _profiles.first.name : null;
          _applyProfile();
          _endpoint ??= _endpoints.isNotEmpty ? _endpoints.first.name : null;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  void _applyProfile() {
    final p = _profiles.where((p) => p.name == _profile).firstOrNull;
    if (p == null) return;
    _workflow = p.workflow ?? _workflow;
    // Profile gates are requests; the checkboxes stay the actual grant.
    _allowWrite = false;
    _allowExec = false;
  }

  Future<void> _runWorkflow() async {
    final goal = _goal.text.trim();
    if (goal.isEmpty || _workflow == null || _endpoint == null || _running) {
      return;
    }
    setState(() {
      _running = true;
      _run = null;
      _error = null;
    });
    try {
      final run = await widget.client.runWorkflow(
        workflow: _workflow!,
        goal: goal,
        endpoint: _endpoint!,
        profile: _profile,
        allowWrite: _allowWrite,
        allowExec: _allowExec,
      );
      if (mounted) setState(() => _run = run);
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
          'The engine is offline. Workflows appear when it runs.',
          command: 'flywheel up');
    }
    final t = context.fw;
    return ViewScroll(
      children: [
        const SectionHeader('Workflows', kicker: 'staged, receipted, any endpoint'),
        const SizedBox(height: FwLayout.s3),
        Text(
          'A profile binds an operating discipline onto the same substrate; '
          'the endpoint is a runtime choice. Older model generations run the '
          'same staged workflow as the newest, and every run folds into one '
          'chained receipt.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: FwLayout.s4),
        _composer(t),
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull('The run failed: $_error'),
        ],
        if (_run != null) ...[
          const SizedBox(height: FwLayout.s4),
          WorkflowRunCard(run: _run!),
        ],
        if ((_roster?.runs.isNotEmpty ?? false)) ...[
          const SizedBox(height: FwLayout.s5),
          const Kicker('recent runs · persisted receipts'),
          const SizedBox(height: FwLayout.s3),
          HairlineCard(
            padding: const EdgeInsets.symmetric(
                horizontal: FwLayout.s4, vertical: FwLayout.s2),
            child: Column(
              children: [for (final r in _roster!.runs) PastRunRow(run: r)],
            ),
          ),
        ],
      ],
    );
  }

  Widget _composer(FwTokens t) {
    final selected =
        _roster?.workflows.where((w) => w.name == _workflow).firstOrNull;
    final activeProfile =
        _profiles.where((p) => p.name == _profile).firstOrNull;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: FwLayout.s4,
            runSpacing: FwLayout.s2,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              _picker('profile', _profile,
                  [for (final p in _profiles) p.name],
                  (v) => setState(() {
                        _profile = v;
                        _applyProfile();
                      })),
              _picker('workflow', _workflow,
                  [for (final w in _roster?.workflows ?? <WorkflowDef>[]) w.name],
                  (v) => setState(() => _workflow = v)),
              _picker('endpoint', _endpoint,
                  [for (final e in _endpoints) e.name],
                  (v) => setState(() => _endpoint = v)),
              _gate('write', _allowWrite, (v) => setState(() => _allowWrite = v)),
              _gate('exec', _allowExec, (v) => setState(() => _allowExec = v)),
            ],
          ),
          if (selected != null) ...[
            const SizedBox(height: FwLayout.s2),
            Text(
                '${selected.description}  Steps: ${selected.stepNames.join(' → ')}',
                style: TextStyle(fontSize: 12, color: t.inkMuted)),
          ],
          if (activeProfile != null) ProfileManifestCard(profile: activeProfile),
          const SizedBox(height: FwLayout.s3),
          TextField(
            controller: _goal,
            maxLines: 3,
            minLines: 2,
            style: const TextStyle(fontSize: 13.5),
            decoration: const InputDecoration(hintText: 'The goal…'),
          ),
          const SizedBox(height: FwLayout.s3),
          FilledButton(
            onPressed: _running ? null : _runWorkflow,
            child: Text(_running ? 'Running…' : 'Run workflow'),
          ),
        ],
      ),
    );
  }

  Widget _picker(String label, String? value, List<String> options,
      ValueChanged<String?> onChanged) {
    final t = context.fw;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Kicker(label),
        const SizedBox(width: FwLayout.s2),
        DropdownButton<String>(
          value: options.contains(value) ? value : null,
          underline: const SizedBox(),
          style: fwMono(t, size: 12, color: t.inkSoft),
          items: [
            for (final o in options) DropdownMenuItem(value: o, child: Text(o)),
          ],
          onChanged: onChanged,
        ),
      ],
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
}
