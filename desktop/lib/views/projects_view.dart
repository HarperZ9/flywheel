import 'dart:async';
import 'package:flutter/material.dart';
import '../client/continuation_api.dart';
import '../client/gateway_client.dart';
import '../client/index_workspace_map_api.dart';
import '../controllers/index_workspace_map_controller.dart';
import '../controllers/journey_controller.dart';
import '../navigation/app_route.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/continuation_agent_sheet.dart';
import '../widgets/continuation_panel.dart';
import '../widgets/flywheel_nav.dart';
import '../widgets/fw.dart';
import '../widgets/import_config_panel.dart';
import '../widgets/project_panels.dart';
import '../widgets/projects_view_parts.dart';

class ProjectsView extends StatefulWidget {
  final GatewayClient client;
  final JourneyController journey;
  final bool alive;
  const ProjectsView({
    super.key,
    required this.client,
    required this.journey,
    required this.alive,
  });
  @override
  State<ProjectsView> createState() => _ProjectsViewState();
}

class _ProjectsViewState extends State<ProjectsView> {
  final _root = TextEditingController();
  List<Map<String, dynamic>> _projects = [];
  Map<String, dynamic>? _store;
  List<Map<String, dynamic>>? _auditTail;
  String? _selected;
  late final IndexWorkspaceMapController _index;
  bool _auditOpen = false;
  String? _error;
  @override
  void initState() {
    super.initState();
    _index = IndexWorkspaceMapController(
      api: GatewayIndexWorkspaceMapApi(widget.client),
    );
    _index.addListener(_indexChanged);
    _load();
  }

  @override
  void didUpdateWidget(ProjectsView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  @override
  void dispose() {
    _index.removeListener(_indexChanged);
    _index.dispose();
    _root.dispose();
    super.dispose();
  }

  void _indexChanged() {
    if (mounted) setState(() {});
  }

  Future<void> _load() async {
    if (!widget.alive) return;
    try {
      final results = await Future.wait([
        widget.client.projects(),
        widget.client.storeStats(),
      ]);
      if (mounted) {
        setState(() {
          _projects = ((results[0]['projects'] ?? []) as List)
              .whereType<Map<String, dynamic>>()
              .toList();
          _store = results[1];
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _add() async {
    final root = _root.text.trim();
    if (root.isEmpty) return;
    try {
      await widget.client.addProject(root);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
      return;
    }
    if (!mounted) return;
    _root.clear();
    setState(() => _error = null);
    _load();
  }

  Future<void> _remove(String root) async {
    try {
      await widget.client.removeProject(root);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
      return;
    }
    if (!mounted) return;
    if (_selected == root) {
      setState(() {
        _selected = null;
      });
      _index.detach();
    }
    _load();
  }

  Future<void> _loadAudit() async {
    try {
      final r = await widget.client.storeAudit(n: 50);
      if (!mounted) return;
      final entries = (r['entries'] is List)
          ? (r['entries'] as List).whereType<Map<String, dynamic>>().toList()
          : <Map<String, dynamic>>[];
      setState(() => _auditTail = entries);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  void _toggleAudit() {
    setState(() => _auditOpen = !_auditOpen);
    if (_auditOpen && _auditTail == null) _loadAudit();
  }

  Future<void> _openIndex(String root) async {
    setState(() => _selected = root);
    await _index.open(root);
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
        'The engine is offline. Projects appear when it runs.',
        command: 'flywheel up',
      );
    }
    final t = context.fw;
    return ViewScroll(
      children: [
        const SectionHeader('Projects', kicker: 'where the work happens'),
        const SizedBox(height: FwLayout.s3),
        Text(
          'Register a project directory once; Flywheel indexes its structure, '
          'maps its knowledge graph, and scopes agents, planning, and memory '
          'to it. Every record lands in the verifiable store below.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull(_error!),
        ],
        const SizedBox(height: FwLayout.s4),
        HairlineCard(
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _root,
                  style: fwMono(t, size: 12.5),
                  decoration: const InputDecoration(
                    hintText: 'Path to a project or monorepo directory…',
                  ),
                  onSubmitted: (_) => _add(),
                ),
              ),
              const SizedBox(width: FwLayout.s3),
              FilledButton(onPressed: _add, child: const Text('Register')),
            ],
          ),
        ),
        const SizedBox(height: FwLayout.s4),
        ImportConfigPanel(client: widget.client),
        const SizedBox(height: FwLayout.s4),
        ContinuationPanel(
          api: GatewayContinuationApi(widget.client),
          alive: widget.alive,
          onContinueWithAgent: (preview, started) async {
            try {
              await showContinuationAgentSheet(
                  context: context,
                  client: widget.client,
                  journey: widget.journey,
                  alive: widget.alive,
                  preview: preview,
                  started: started);
            } catch (error) {
              if (mounted) setState(() => _error = '$error');
              rethrow;
            }
          },
          onOpenJourney: (ref, lens) {
            unawaited(widget.journey.openSession(ref, lens));
            FlywheelNav.jump(context, DestinationId.journey);
          },
        ),
        const SizedBox(height: FwLayout.s4),
        for (final p in _projects)
          ProjectRowCard(
            project: p,
            selectedRoot: _selected,
            indexBusy: _index.busy,
            onIndex: _openIndex,
            onRemove: _remove,
          ),
        if (_selected != null) ...[
          const SizedBox(height: FwLayout.s5),
          const Kicker('index · catalog + knowledge graph', hot: true),
          const SizedBox(height: FwLayout.s3),
          IndexPanel(
            summary: _index.summary,
            job: _index.job,
            busy: _index.busy,
            message: _index.message,
            onCancel: _index.cancel,
            onRefresh: _index.refreshStatus,
            onResult: _index.retrieveResult,
            onResume: _index.resume,
            onUpdate: _index.updateWorkspaceMap,
          ),
        ],
        if (_store != null) ...[
          const SizedBox(height: FwLayout.s5),
          const Kicker('verifiable store · content-addressed, chained'),
          const SizedBox(height: FwLayout.s3),
          StorePanel(
            store: _store!,
            onVerify: () async {
              Map<String, dynamic> v;
              try {
                v = await widget.client.storeVerify();
              } catch (e) {
                if (mounted) setState(() => _error = '$e');
                return;
              }
              if (mounted) {
                final chain = v['chain'] is Map ? v['chain'] as Map : const {};
                final records =
                    v['records'] is Map ? v['records'] as Map : const {};
                setState(
                  () => _error = v['ok'] == true
                      ? 'audit chain verified: ${chain['checked'] ?? 0} '
                          'entries, ${records['checked'] ?? 0} records '
                          're-checked against their hashes'
                      : 'CHAIN BROKEN at ${chain['broken_at'] ?? '?'}: '
                          '${chain['reason'] ?? 'a record no longer matches its hash'}',
                );
              }
            },
          ),
          const SizedBox(height: FwLayout.s3),
          ProjectsAuditSection(
            open: _auditOpen,
            entries: _auditTail,
            onToggle: _toggleAudit,
          ),
        ],
      ],
    );
  }
}
