// projects_view.dart — the productive home: register project directories,
// then read each one's monorepo catalog and knowledge graph straight from
// the index engine, over the verifiable store substrate. This is where work
// starts — a project, its structure, its provenance.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import '../widgets/project_panels.dart';

class ProjectsView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const ProjectsView({super.key, required this.client, required this.alive});

  @override
  State<ProjectsView> createState() => _ProjectsViewState();
}

class _ProjectsViewState extends State<ProjectsView> {
  final _root = TextEditingController();
  List<Map<String, dynamic>> _projects = [];
  Map<String, dynamic>? _store;
  String? _selected;
  Map<String, dynamic>? _index;
  bool _indexing = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(ProjectsView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  @override
  void dispose() {
    _root.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (!widget.alive) return;
    try {
      final results =
          await Future.wait([widget.client.projects(), widget.client.storeStats()]);
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
    final r = await widget.client.addProject(root);
    if (r['error'] != null) {
      setState(() => _error = '${r['error']}');
    } else {
      _root.clear();
      _error = null;
      _load();
    }
  }

  Future<void> _openIndex(String root) async {
    setState(() {
      _selected = root;
      _index = null;
      _indexing = true;
    });
    try {
      final r = await widget.client.indexProject(root, view: 'summary');
      if (mounted) setState(() => _index = r);
    } catch (e) {
      if (mounted) setState(() => _index = {'errors': {'index': '$e'}});
    } finally {
      if (mounted) setState(() => _indexing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. Projects appear when it runs.',
          command: 'flywheel up');
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
                      hintText: 'Path to a project or monorepo directory…'),
                  onSubmitted: (_) => _add(),
                ),
              ),
              const SizedBox(width: FwLayout.s3),
              FilledButton(onPressed: _add, child: const Text('Register')),
            ],
          ),
        ),
        const SizedBox(height: FwLayout.s4),
        for (final p in _projects) _projectCard(t, p),
        if (_selected != null) ...[
          const SizedBox(height: FwLayout.s5),
          const Kicker('index · catalog + knowledge graph', hot: true),
          const SizedBox(height: FwLayout.s3),
          IndexPanel(index: _index, indexing: _indexing),
        ],
        if (_store != null) ...[
          const SizedBox(height: FwLayout.s5),
          const Kicker('verifiable store · content-addressed, chained'),
          const SizedBox(height: FwLayout.s3),
          StorePanel(
              store: _store!,
              onVerify: () async {
                final v = await widget.client.storeVerify();
                if (mounted) {
                  // the gateway nests the two walks: chain (ledger links)
                  // and records (content re-hash); read both defensively.
                  final chain =
                      v['chain'] is Map ? v['chain'] as Map : const {};
                  final records =
                      v['records'] is Map ? v['records'] as Map : const {};
                  setState(() => _error = v['ok'] == true
                      ? 'audit chain verified: ${chain['checked'] ?? 0} '
                          'entries, ${records['checked'] ?? 0} records '
                          're-checked against their hashes'
                      : 'CHAIN BROKEN at ${chain['broken_at'] ?? '?'}: '
                          '${chain['reason'] ?? 'a record no longer matches its hash'}');
                }
              }),
        ],
      ],
    );
  }

  Widget _projectCard(FwTokens t, Map<String, dynamic> p) {
    final root = '${p['root']}';
    final exists = p['exists'] == true;
    final selected = root == _selected;
    return Padding(
      padding: const EdgeInsets.only(bottom: FwLayout.s3),
      child: HairlineCard(
        recessed: selected,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text('${p['name']}',
                      style: const TextStyle(
                          fontSize: 15, fontWeight: FontWeight.w700)),
                ),
                VerdictPill('${p['kind']}', status: 'unverifiable'),
                const SizedBox(width: FwLayout.s2),
                VerdictPill(exists ? 'present' : 'missing',
                    status: exists ? 'verified' : 'drift'),
              ],
            ),
            const SizedBox(height: FwLayout.s1),
            Text(root, style: fwMono(t, size: 11, color: t.inkFaint)),
            const SizedBox(height: FwLayout.s3),
            Row(
              children: [
                FilledButton.tonal(
                  onPressed: exists ? () => _openIndex(root) : null,
                  child: Text(selected && _indexing ? 'Indexing…' : 'Index'),
                ),
                const SizedBox(width: FwLayout.s3),
                OutlinedButton(
                  onPressed: () async {
                    await widget.client.removeProject(root);
                    if (_selected == root) {
                      setState(() {
                        _selected = null;
                        _index = null;
                      });
                    }
                    _load();
                  },
                  child: const Text('Remove'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

}
