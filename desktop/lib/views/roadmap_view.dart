// roadmap_view.dart -- the Roadmap destination: one page a manager reads.
//
// Goals are swarm goals; each sealed receipt carries its per-child
// verification status and quorum verdict; open rows stay visible instead
// of disappearing. The verification floor (bound skill gates, sealed vs
// open goals) sits under the table, and the page prints its own
// does-not-prove notes -- a roadmap that hides what it does not know is a
// fiction with formatting.
import 'package:flutter/material.dart';

import '../client/gateway_error.dart';
import '../client/gateway_roadmap.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class RoadmapView extends StatefulWidget {
  final RoadmapApi api;
  final bool alive;
  const RoadmapView({super.key, required this.api, required this.alive});

  @override
  State<RoadmapView> createState() => _RoadmapViewState();
}

class _RoadmapViewState extends State<RoadmapView> {
  Map<String, dynamic>? _roadmap;
  List<Map<String, dynamic>> _goals = [];
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() => _busy = true);
    try {
      final body = await widget.api.roadmap();
      final doc = body['roadmap'];
      final goals = doc is Map && doc['goals'] is List
          ? (doc['goals'] as List)
              .whereType<Map>()
              .map(_asMap)
              .toList()
          : <Map<String, dynamic>>[];
      setState(() {
        _roadmap = doc is Map ? _asMap(doc) : null;
        _goals = goals;
        _error = null;
      });
    } on GatewayException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error = 'the roadmap could not be read');
    } finally {
      setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. Start it to read the roadmap.',
          command: 'flywheel up');
    }
    final t = context.fw;
    return ViewScroll(storageKey: 'roadmap', children: [
      Row(children: [
        const Expanded(child: SectionHeader('Roadmap', kicker: 'manager view')),
        IconButton(
          key: const Key('roadmap-refresh'),
          onPressed: _busy ? null : _refresh,
          tooltip: 'Rebuild from sealed receipts',
          icon: const Icon(Icons.refresh),
        ),
      ]),
      const SizedBox(height: FwLayout.s3),
      Text(
        'Goals are swarm goals; verified children come from sealed run '
        'receipts; the floor counts bound skill gates. Open rows are '
        'known-running or detached work, not estimates.',
        style: TextStyle(fontSize: 13, height: 1.5, color: t.inkMuted),
      ),
      const SizedBox(height: FwLayout.s4),
      if (_error != null)
        Padding(
          padding: const EdgeInsets.only(bottom: FwLayout.s3),
          child: HonestNull(_error!),
        ),
      if (_roadmap == null && !_busy)
        const HonestNull('No roadmap yet; seal a swarm or bind a skill.')
      else if (_roadmap != null) ...[
        HairlineCard(child: _goalsTable(context)),
        const SizedBox(height: FwLayout.s3),
        HairlineCard(child: _floor(context)),
        const SizedBox(height: FwLayout.s3),
        ..._limits(context),
      ],
    ]);
  }

  Widget _goalsTable(BuildContext context) {
    final t = context.fw;
    if (_goals.isEmpty) {
      return const Padding(
        padding: EdgeInsets.all(FwLayout.s3),
        child: HonestNull('No goals yet. Spawn a swarm and it lands here.'),
      );
    }
    return Padding(
      padding: const EdgeInsets.all(FwLayout.s3),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        for (final g in _goals) ...[
          Row(children: [
            VerdictDot(_stateStatus(g['state']?.toString())),
            const SizedBox(width: FwLayout.s2),
            Expanded(
                child: Text('${g['ref'] ?? ''}',
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 12, color: t.ink))),
            Text('${g['verified_children'] ?? '-'}',
                style: TextStyle(fontSize: 12, color: t.inkMuted)),
            const SizedBox(width: FwLayout.s2),
            if ((g['verdict'] as String?)?.isNotEmpty == true)
              VerdictPill(g['verdict'],
                  status:
                      g['verdict'] == 'satisfied' ? 'verified' : 'pending')
            else
              Text('${g['state'] ?? ''}',
                  style: TextStyle(fontSize: 12, color: t.inkMuted)),
          ]),
          const SizedBox(height: FwLayout.s1),
        ],
      ]),
    );
  }

  Widget _floor(BuildContext context) {
    final v = (_roadmap?['verification'] as Map?) ?? {};
    return Padding(
      padding: const EdgeInsets.all(FwLayout.s3),
      child: Wrap(spacing: FwLayout.s4, runSpacing: FwLayout.s2, children: [
        StatTile(
            label: 'Skills bound',
            value: '${v['skills_bound'] ?? 0}'),
        StatTile(
            label: 'Sealed goals',
            value: '${v['sealed_goals'] ?? 0}'),
        StatTile(label: 'Open goals', value: '${v['open_goals'] ?? 0}'),
      ]),
    );
  }

  List<Widget> _limits(BuildContext context) {
    final notes = ((_roadmap?['does_not_prove'] as List?) ?? [])
        .whereType<Object>()
        .map((n) => n.toString())
        .toList();
    if (notes.isEmpty) return const [];
    return [
      for (final note in notes)
        Padding(
          padding: const EdgeInsets.only(bottom: FwLayout.s1),
          child: HonestNull(note),
        ),
    ];
  }
}

/// Status maps onto the verdict palette; satisfied is the accept mark,
/// open states are unverifiable grey, drift is the caution verdict.
String _stateStatus(String? state) {
  switch (state) {
    case 'sealed':
      return 'verified';
    case 'running':
    case 'detached':
      return 'pending';
    default:
      return 'drift';
  }
}

Map<String, dynamic> _asMap(Map<dynamic, dynamic> m) =>
    m.map((k, v) => MapEntry(k.toString(), v));
