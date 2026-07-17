// workflows_view.dart — staged runs over any endpoint, shaped by a profile
// manifest. Every step carries its own verdict and the whole run carries one
// chained receipt. A verify step without an exec grant says UNVERIFIABLE;
// nothing here dresses up an unproven result.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../models/workflow_models.dart';
import '../services/settings.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/composer_controls.dart';
import '../widgets/composer_results.dart';
import '../widgets/fw.dart';
import '../widgets/workflow_cards.dart';

class WorkflowsView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  final DesktopSettings settings;
  const WorkflowsView(
      {super.key,
      required this.client,
      required this.alive,
      required this.settings});

  @override
  State<WorkflowsView> createState() => _WorkflowsViewState();
}

class _WorkflowsViewState extends State<WorkflowsView> {
  final _goal = TextEditingController();
  final _root = TextEditingController();
  final _testCmd = TextEditingController();
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
  WorkflowRun? _trace; // a STORED run opened from history
  bool? _traceOk;
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
    _root.dispose();
    _testCmd.dispose();
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
        root: _root.text.trim(),
        testCmd: _testCmd.text.trim(),
      );
      if (mounted) setState(() => _run = run);
      _load(); // the new run's receipt belongs in history immediately
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  /// Open one stored run's full per-stage trace, chain-reverified at read.
  Future<void> _openTrace(Map<String, dynamic> row) async {
    final chain = '${row['chain_hash'] ?? ''}';
    if (chain.length < 4) return;
    try {
      final doc = await widget.client.workflowRunDetail(chain);
      if (mounted) {
        setState(() {
          _trace = WorkflowRun.fromJson(doc);
          _traceOk = doc['chain_ok'] == true;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
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
    return ComposerResults(
      settings: widget.settings,
      viewKey: 'workflows',
      header: const SectionHeader('Workflows',
          kicker: 'staged, receipted, any endpoint'),
      composer: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(
          'A profile binds an operating discipline onto the same substrate; '
          'the endpoint is a runtime choice. Older model generations run the '
          'same staged workflow as the newest, and every run folds into one '
          'chained receipt.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: FwLayout.s4),
        _composer(t),
      ]),
      results: [
        if (_error != null) HonestNull('The run failed: $_error'),
        if (_run != null) WorkflowRunCard(run: _run!),
        if ((_roster?.runs.isNotEmpty ?? false)) ...[
          const SizedBox(height: FwLayout.s5),
          const Kicker('recent runs · persisted receipts, tap for the trace'),
          const SizedBox(height: FwLayout.s3),
          HairlineCard(
            padding: const EdgeInsets.symmetric(
                horizontal: FwLayout.s4, vertical: FwLayout.s2),
            child: Column(
              children: [
                for (final r in _roster!.runs)
                  PastRunRow(run: r, onTap: () => _openTrace(r)),
              ],
            ),
          ),
        ],
        if (_trace != null) ...[
          const SizedBox(height: FwLayout.s4),
          const Kicker('stored trace · re-verified at read'),
          const SizedBox(height: FwLayout.s3),
          if (_traceOk == false) ...[
            const HonestNull(
                'This receipt failed re-verification: its content no longer '
                'matches its chain hash. It is served as TAMPERED.'),
            const SizedBox(height: FwLayout.s3),
          ],
          WorkflowRunCard(run: _trace!),
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
          const SizedBox(height: FwLayout.s2),
          Row(children: [
            Expanded(
              child: TextField(
                controller: _root,
                style: fwMono(t, size: 12),
                decoration: const InputDecoration(
                    hintText: r'workspace root (optional), e.g. C:\dev\proj'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            Expanded(
              child: TextField(
                controller: _testCmd,
                style: fwMono(t, size: 12),
                decoration: const InputDecoration(
                    hintText: 'verify command, e.g. pytest -q — without it '
                        'the verify stage can only say UNVERIFIABLE'),
              ),
            ),
          ]),
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
          ValueChanged<String?> onChanged) =>
      LabeledPicker(
          label: label, value: value, options: options, onChanged: onChanged);

  Widget _gate(String label, bool value, ValueChanged<bool> onChanged) =>
      GrantCheckbox(label: label, value: value, onChanged: onChanged);
}
