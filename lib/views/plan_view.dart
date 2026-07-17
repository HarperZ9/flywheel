// plan_view.dart — spec-driven planning: a goal becomes a criterion-bearing
// plan BEFORE anything runs. The forge scores confidence by how many of the
// plan's validation gates an external oracle can run (checkability is the
// verdict), the deep profile supplies the discipline and the workflow, the
// registered project supplies the root, and the handoff is a staged run that
// carries one chained receipt.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../models/plan_models.dart';
import '../models/workflow_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import '../widgets/plan_cards.dart';
import '../widgets/workflow_cards.dart';

class PlanView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const PlanView({super.key, required this.client, required this.alive});

  @override
  State<PlanView> createState() => _PlanViewState();
}

class _PlanViewState extends State<PlanView> {
  final _goal = TextEditingController();
  List<Map<String, dynamic>> _projects = [];
  List<ProfileManifest> _profiles = [];
  List<EndpointRow> _endpoints = [];
  String? _root;
  String? _profile;
  String? _endpoint;
  bool _allowWrite = false;
  bool _allowExec = false;
  bool _forging = false;
  bool _running = false;
  ForgedPlan? _plan;
  WorkflowRun? _run;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(PlanView old) {
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
        widget.client.projects(),
        widget.client.profiles(),
        widget.client.endpointRoster(),
      ]);
      if (mounted) {
        setState(() {
          _projects = ((results[0] as Map<String, dynamic>)['projects'] ?? [])
              .whereType<Map<String, dynamic>>()
              .toList()
              .cast<Map<String, dynamic>>();
          _profiles = results[1] as List<ProfileManifest>;
          _endpoints = results[2] as List<EndpointRow>;
          _root ??= _projects.isNotEmpty ? '${_projects.first['root']}' : null;
          _profile ??= _profiles.isNotEmpty ? _profiles.first.name : null;
          _endpoint ??= _endpoints.isNotEmpty ? _endpoints.first.name : null;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  ProfileManifest? get _activeProfile =>
      _profiles.where((p) => p.name == _profile).firstOrNull;

  Future<void> _forge() async {
    final goal = _goal.text.trim();
    if (goal.isEmpty || _forging) return;
    setState(() {
      _forging = true;
      _plan = null;
      _run = null;
      _error = null;
    });
    try {
      final p = _activeProfile;
      final ctx = [
        if (_root != null) 'Project root: $_root.',
        if (p != null) 'Discipline (${p.name}): ${p.planning.join(' -> ')}.',
      ].join(' ');
      final plan = ForgedPlan.fromJson(
          await widget.client.forge(goal, context: ctx.isEmpty ? null : ctx));
      if (mounted) {
        setState(() {
          if (plan.error != null) {
            _error = plan.error;
          } else {
            _plan = plan;
          }
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _forging = false);
    }
  }

  Future<void> _runPlan() async {
    final p = _activeProfile;
    if (_plan == null || p?.workflow == null || _endpoint == null ||
        _root == null || _running) {
      return;
    }
    setState(() {
      _running = true;
      _run = null;
      _error = null;
    });
    try {
      final run = await widget.client.runWorkflow(
        workflow: p!.workflow!,
        goal: _plan!.goal,
        endpoint: _endpoint!,
        profile: _profile,
        allowWrite: _allowWrite,
        allowExec: _allowExec,
        root: _root,
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
      return const FwEmpty('The engine is offline. Plan appears when it runs.',
          command: 'flywheel up');
    }
    final t = context.fw;
    return ViewScroll(
      children: [
        const SectionHeader('Plan', kicker: 'spec first, receipt after'),
        const SizedBox(height: FwLayout.s3),
        Text(
          'The forge turns a goal into a plan whose validation gates are '
          'marked by what an external oracle can actually run; confidence is '
          'that ratio, not a vibe. The profile binds the discipline, the '
          'project binds the root, and the run carries one chained receipt.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: FwLayout.s4),
        _composer(t),
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull('Failed: $_error'),
        ],
        if (_plan != null) ...[
          const SizedBox(height: FwLayout.s4),
          ForgedPlanCard(
              plan: _plan!,
              profile: _activeProfile,
              recheck: widget.client.forgeRecheck),
        ],
        if (_run != null) ...[
          const SizedBox(height: FwLayout.s4),
          WorkflowRunCard(run: _run!),
        ],
      ],
    );
  }

  Widget _composer(FwTokens t) {
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: FwLayout.s4,
            runSpacing: FwLayout.s2,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              _picker('project', _root,
                  [for (final p in _projects) '${p['root']}'],
                  (v) => setState(() => _root = v)),
              _picker('profile', _profile,
                  [for (final p in _profiles) p.name],
                  (v) => setState(() => _profile = v)),
              _picker('endpoint', _endpoint,
                  [for (final e in _endpoints) e.name],
                  (v) => setState(() => _endpoint = v)),
              _gate('write', _allowWrite, (v) => setState(() => _allowWrite = v)),
              _gate('exec', _allowExec, (v) => setState(() => _allowExec = v)),
            ],
          ),
          if (_projects.isEmpty) ...[
            const SizedBox(height: FwLayout.s2),
            Text(
                'No project registered. Forging works without one; running '
                'the plan does not. Register a directory under Projects.',
                style: fwMono(t, size: 11.5, color: t.inkMuted)),
          ],
          const SizedBox(height: FwLayout.s3),
          TextField(
            controller: _goal,
            maxLines: 3,
            minLines: 2,
            style: const TextStyle(fontSize: 13.5),
            decoration: const InputDecoration(hintText: 'The goal…'),
          ),
          const SizedBox(height: FwLayout.s3),
          Row(
            children: [
              FilledButton(
                onPressed: _forging ? null : _forge,
                child: Text(_forging ? 'Forging…' : 'Forge plan'),
              ),
              const SizedBox(width: FwLayout.s3),
              OutlinedButton(
                onPressed: _plan == null || _running ||
                        _activeProfile?.workflow == null ||
                        _root == null || _endpoint == null
                    ? null
                    : _runPlan,
                child: Text(_running
                    ? 'Running…'
                    : 'Run as ${_activeProfile?.workflow ?? 'workflow'}'),
              ),
            ],
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
