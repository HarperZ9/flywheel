// graph_view.dart — the Graph view: the cross-surface knowledge graph the
// developer, the model, and the desktop all read the same way. Nodes are
// live surfaces with engine-computed priorities; a budget turns the graph
// into a context plan whose exclusions stay counted. Pan and zoom are
// native; a tapped node opens its signals in a resizable detail pane.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/graph_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import '../widgets/graph_canvas.dart';
import '../widgets/split_pane.dart';

class GraphView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const GraphView({super.key, required this.client, required this.alive});

  @override
  State<GraphView> createState() => _GraphViewState();
}

class _GraphViewState extends State<GraphView> {
  final _budget = TextEditingController(text: '2000');
  final _query = TextEditingController();
  KnowledgeGraph? _graph;
  GraphNode? _selected;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(GraphView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  @override
  void dispose() {
    _budget.dispose();
    _query.dispose();
    super.dispose();
  }

  Future<void> _load({bool withBudget = false}) async {
    if (!widget.alive || _loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final budget = int.tryParse(_budget.text.trim());
      final q = _query.text.trim();
      final path = withBudget && budget != null
          ? '/api/graph?budget=$budget'
              '${q.isEmpty ? '' : '&q=${Uri.encodeQueryComponent(q)}'}'
          : '/api/graph';
      final g = KnowledgeGraph.fromJson(await widget.client.getJson(path));
      if (mounted) setState(() => _graph = g);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. The graph draws from live state.',
          command: 'flywheel up');
    }
    final t = context.fw;
    final g = _graph;
    return Padding(
      padding: const EdgeInsets.symmetric(
          horizontal: FwLayout.s6, vertical: FwLayout.s5),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader('Graph',
              kicker: 'every surface, one graph, priced context',
              trailing: _controls(t)),
          const SizedBox(height: FwLayout.s3),
          if (_error != null) ...[
            HonestNull('Failed: $_error'),
            const SizedBox(height: FwLayout.s3),
          ],
          Expanded(
            child: g == null
                ? const Center(
                    child: CircularProgressIndicator(strokeWidth: 2))
                : SplitPane(
                    axis: Axis.horizontal,
                    initialFraction: 0.72,
                    minFraction: 0.4,
                    maxFraction: 0.85,
                    first: HairlineCard(
                      padding: EdgeInsets.zero,
                      child: ClipRRect(
                        borderRadius:
                            BorderRadius.circular(FwLayout.radius),
                        child: InteractiveViewer(
                          minScale: 0.5,
                          maxScale: 4,
                          child: GraphCanvas(
                            graph: g,
                            selectedId: _selected?.id,
                            onSelect: (n) =>
                                setState(() => _selected = n),
                          ),
                        ),
                      ),
                    ),
                    second: _detail(t, g),
                  ),
          ),
          const SizedBox(height: FwLayout.s2),
          _legend(t),
        ],
      ),
    );
  }

  Widget _controls(FwTokens t) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Kicker('query'),
        const SizedBox(width: FwLayout.s2),
        SizedBox(
          width: 160,
          child: TextField(
            controller: _query,
            style: fwMono(t, size: 12),
            decoration: const InputDecoration(
                isDense: true, hintText: 'rerank terms…'),
          ),
        ),
        const SizedBox(width: FwLayout.s3),
        const Kicker('budget'),
        const SizedBox(width: FwLayout.s2),
        SizedBox(
          width: 72,
          child: TextField(
            controller: _budget,
            style: fwMono(t, size: 12),
            decoration: const InputDecoration(isDense: true),
          ),
        ),
        const SizedBox(width: FwLayout.s3),
        OutlinedButton(
          onPressed: _loading ? null : () => _load(withBudget: true),
          child: const Text('Plan context'),
        ),
        const SizedBox(width: FwLayout.s2),
        OutlinedButton(
          onPressed: _loading ? null : _load,
          child: const Text('Refresh'),
        ),
      ],
    );
  }

  Widget _detail(FwTokens t, KnowledgeGraph g) {
    final n = _selected;
    return HairlineCard(
      recessed: true,
      child: n == null
          ? Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Kicker('detail'),
                const SizedBox(height: FwLayout.s2),
                Text(
                    '${g.nodes.length} nodes, ${g.edges.length} edges. '
                    'Tap a node for its signals.',
                    style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
                if (g.plan != null) ...[
                  const SizedBox(height: FwLayout.s3),
                  const Kicker('context plan', hot: true),
                  const SizedBox(height: FwLayout.s2),
                  Text(
                      'spent ${g.plan!.spent}/${g.plan!.budget} tokens · '
                      '${g.plan!.selectedIds.length} in, '
                      '${g.plan!.excluded} cut (counted, not hidden)',
                      style: fwMono(t, size: 11.5, color: t.inkSoft)),
                ],
              ],
            )
          : ListView(
              children: [
                Kicker(n.kind, hot: true),
                const SizedBox(height: FwLayout.s2),
                Text(n.label,
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: FwLayout.s2),
                VerdictPill(statusOf(n), status: statusOf(n)),
                const SizedBox(height: FwLayout.s3),
                Text('priority ${n.priority} · cost ~${n.cost} tokens',
                    style: fwMono(t, size: 11.5, color: t.inkSoft)),
                if (g.plan != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(
                        g.plan!.selectedIds.contains(n.id)
                            ? 'inside the context plan'
                            : 'cut by the budget',
                        style: fwMono(t, size: 11.5, color: t.inkMuted)),
                  ),
                const SizedBox(height: FwLayout.s3),
                const Kicker('signals'),
                const SizedBox(height: FwLayout.s2),
                for (final e in n.signals.entries)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Text('${e.key} = ${e.value}',
                        style: fwMono(t, size: 11.5, color: t.inkSoft)),
                  ),
                if (n.signals.isEmpty)
                  Text('(none)',
                      style: fwMono(t, size: 11.5, color: t.inkFaint)),
              ],
            ),
    );
  }

  Widget _legend(FwTokens t) {
    Widget item(String label) => Padding(
          padding: const EdgeInsets.only(right: FwLayout.s3),
          child: Text(label, style: fwMono(t, size: 10.5, color: t.inkMuted)),
        );
    return Wrap(
      children: [
        item('circle lane'),
        item('square project'),
        item('diamond memory'),
        item('triangle plugin'),
        item('x unreadable surface'),
        item('size = priority'),
        item('green ring = in context plan'),
      ],
    );
  }
}
