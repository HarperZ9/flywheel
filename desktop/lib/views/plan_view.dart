import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../client/gateway_plan.dart';
import '../controllers/plan_controller.dart';
import '../models/gateway_models.dart';
import '../models/plan_models.dart';
import '../models/plan_run_models.dart';
import '../models/workflow_models.dart';
import '../services/settings.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/composer_results.dart';
import '../widgets/fw.dart';
import '../widgets/operation_grant_sheet.dart';
import '../widgets/plan_cards.dart';
import '../widgets/plan_run_controls.dart';
import '../widgets/workflow_cards.dart';

class PlanView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  final DesktopSettings settings;
  const PlanView(
      {super.key,
      required this.client,
      required this.alive,
      required this.settings});
  @override
  State<PlanView> createState() => _PlanViewState();
}

class _PlanViewState extends State<PlanView> {
  final _goal = TextEditingController();
  late final GatewayPlan _gateway;
  late final PlanController _controller;
  List<Map<String, dynamic>> _projects = [];
  List<ProfileManifest> _profiles = [];
  List<EndpointRow> _endpoints = [];
  String? _root, _profile, _endpoint, _loadError;
  bool _allowWrite = false, _allowExec = false;

  @override
  void initState() {
    super.initState();
    _gateway = GatewayPlan(widget.client);
    _controller = PlanController(_gateway)..addListener(_planChanged);
    _load();
  }

  @override
  void didUpdateWidget(PlanView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  @override
  void dispose() {
    _controller.removeListener(_planChanged);
    _controller.dispose();
    _goal.dispose();
    super.dispose();
  }

  void _planChanged() {
    if (mounted) setState(() {});
  }

  Future<void> _load() async {
    if (!widget.alive) return;
    try {
      final results = await Future.wait([
        widget.client.projects(),
        widget.client.profiles(),
        widget.client.endpointRoster(),
      ]);
      if (!mounted) return;
      setState(() {
        _projects = ((results[0] as Map<String, dynamic>)['projects'] ?? [])
            .whereType<Map<String, dynamic>>()
            .toList();
        _profiles = results[1] as List<ProfileManifest>;
        _endpoints = results[2] as List<EndpointRow>;
        _root ??= _projects.isNotEmpty ? '${_projects.first['root']}' : null;
        _profile ??= _profiles.isNotEmpty ? _profiles.first.name : null;
        _endpoint ??= _endpoints.isNotEmpty ? _endpoints.first.name : null;
        _loadError = null;
      });
    } catch (error) {
      if (mounted) setState(() => _loadError = '$error');
    }
  }

  ProfileManifest? get _activeProfile =>
      _profiles.where((item) => item.name == _profile).firstOrNull;

  ForgedPlan? get _plan {
    final binding = _controller.binding;
    if (binding == null) return null;
    return ForgedPlan.fromJson(
        <String, dynamic>{...binding.prp, 'prp_id': binding.prpId});
  }

  WorkflowRun? get _workflowRun {
    final result = _controller.result;
    return result == null
        ? null
        : WorkflowRun.fromJson(Map<String, dynamic>.from(result.workflowRun));
  }

  Future<void> _forge() async {
    final goal = _goal.text.trim();
    if (goal.isEmpty) return;
    final profile = _activeProfile;
    final forgeContext = [
      if (_root != null) 'A registered project is selected.',
      if (profile != null && profile.planning.isNotEmpty)
        'Discipline (${profile.name}): ${profile.planning.join(' -> ')}.',
    ].join(' ');
    await _controller.forge(goal,
        context: forgeContext.isEmpty ? null : forgeContext);
  }

  PlanRunRequest? _request(String requestId) {
    final binding = _controller.binding;
    final profile = _activeProfile;
    if (binding == null ||
        profile?.workflow == null ||
        _root == null ||
        _endpoint == null) {
      return null;
    }
    return PlanRunRequest(
        workflow: profile!.workflow!,
        profile: profile.name,
        root: _root!,
        endpoint: _endpoint!,
        allowWrite: _allowWrite,
        allowExec: _allowExec,
        binding: binding,
        dataRefs: const [],
        credentialRefs: const [],
        clientRequestId: requestId);
  }

  Future<void> _runPlan() async {
    final requestId = 'desktop-plan-${DateTime.now().microsecondsSinceEpoch}';
    final request = _request(requestId);
    if (request == null) return;
    await _controller.run(request,
        currentRequest: () => _request(requestId),
        authorize: (operation, current, dispatch) =>
            authorizeGatewayOperationDetailed<PlanRunResult>(
                context, operation, dispatch,
                currentOperation: current));
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty('Engine offline.', command: 'flywheel up');
    }
    final plan = _plan;
    final run = _workflowRun;
    return ComposerResults(
      settings: widget.settings,
      viewKey: 'plan',
      header: const SectionHeader('Plan', kicker: 'spec first, receipt after'),
      composer:
          Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text('Forge a plan, then approve its exact bound workflow run.',
            style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: FwLayout.s4),
        _composer(context.fw),
      ]),
      results: [
        if (_loadError != null) HonestNull('Failed: $_loadError'),
        if (plan != null)
          ForgedPlanCard(
              plan: plan,
              profile: _activeProfile,
              recheck: (prpId) => _gateway.recheck(prpId)),
        if (run != null) ...[
          const SizedBox(height: FwLayout.s4),
          WorkflowRunCard(run: run),
        ],
      ],
    );
  }

  Widget _composer(FwTokens tokens) => HairlineCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(
              spacing: FwLayout.s4,
              runSpacing: FwLayout.s2,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                _picker(
                    'project',
                    _root,
                    [for (final item in _projects) '${item['root']}'],
                    (value) => setState(() => _root = value)),
                _picker(
                    'profile',
                    _profile,
                    [for (final item in _profiles) item.name],
                    (value) => setState(() => _profile = value)),
                _picker(
                    'endpoint',
                    _endpoint,
                    [for (final item in _endpoints) item.name],
                    (value) => setState(() => _endpoint = value)),
                _gate('write', _allowWrite,
                    (value) => setState(() => _allowWrite = value)),
                _gate('exec', _allowExec,
                    (value) => setState(() => _allowExec = value)),
              ]),
          if (_projects.isEmpty) ...[
            const SizedBox(height: FwLayout.s2),
            Text(
                'No project registered. Forging works without one; running '
                'the plan does not. Register a directory under Projects.',
                style: fwMono(tokens, size: 11.5, color: tokens.inkMuted)),
          ],
          const SizedBox(height: FwLayout.s3),
          TextField(
              controller: _goal,
              onChanged: (_) => setState(() {}),
              maxLines: 3,
              minLines: 2,
              style: const TextStyle(fontSize: 13.5),
              decoration: const InputDecoration(hintText: 'The goal…')),
          const SizedBox(height: FwLayout.s3),
          PlanRunControls(
              controller: _controller,
              canForge: _goal.text.trim().isNotEmpty,
              canRun: _request('preview') != null,
              runLabel: 'Run as ${_activeProfile?.workflow ?? 'workflow'}',
              onForge: _forge,
              onRun: _runPlan),
        ]),
      );

  Widget _picker(String label, String? value, List<String> options,
          ValueChanged<String?> changed) =>
      Row(mainAxisSize: MainAxisSize.min, children: [
        Kicker(label),
        const SizedBox(width: FwLayout.s2),
        DropdownButton<String>(
            value: options.contains(value) ? value : null,
            underline: const SizedBox(),
            style: fwMono(context.fw, size: 12, color: context.fw.inkSoft),
            items: [
              for (final option in options)
                DropdownMenuItem(value: option, child: Text(option)),
            ],
            onChanged: changed),
      ]);

  Widget _gate(String label, bool value, ValueChanged<bool> changed) =>
      Row(mainAxisSize: MainAxisSize.min, children: [
        Checkbox(
            value: value,
            onChanged: (next) => changed(next ?? false),
            visualDensity: VisualDensity.compact),
        Text('allow $label',
            style: fwMono(context.fw, size: 11.5, color: context.fw.inkMuted)),
      ]);
}
