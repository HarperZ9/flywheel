// lane_health_panel.dart — compact lane readiness and details widgets for the
// public Tools surface. Rows show state and facts first; each open card holds
// that lane's console, where every tool call goes through its own approval.
// One lane's card lives in lane_card.dart, its console in lane_console.dart.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../models/lane_readiness.dart';
import '../models/lane_state.dart';
import '../theme/flywheel_theme.dart';
import 'callable_lanes_panel.dart';
import 'fw.dart';
import 'lane_card.dart';
import 'lane_console.dart';

class LaneReadinessPanel extends StatelessWidget {
  final int total;
  final Map<String, int> counts;
  final String detail;

  /// Whether [counts] holds engine states rather than presence statuses.
  final bool stateCounts;
  const LaneReadinessPanel({
    super.key,
    required this.total,
    required this.counts,
    required this.detail,
    this.stateCounts = false,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Expanded(child: Kicker('installed/readiness')),
          Text('$total registry lanes',
              style: fwMono(t, size: 11.5, color: t.inkMuted)),
        ]),
        const SizedBox(height: FwLayout.s2),
        Text(detail, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: FwLayout.s3),
        Wrap(
          spacing: FwLayout.s2,
          runSpacing: FwLayout.s2,
          children: [
            if (stateCounts)
              for (final entry in counts.entries)
                VerdictPill(
                    '${entry.value} ${laneCountPhrase(entry.key, entry.value)}',
                    status: laneCountVerdict(entry.key))
            else
              for (final entry in _statusEntries(counts))
                VerdictPill('${entry.value} ${entry.key}', status: entry.key),
          ],
        ),
        const SizedBox(height: FwLayout.s3),
        Text(
          'Probe now starts every lane and lists its tools. A lane reads '
          'ready only when one of its main tools can run here. Setup is '
          'stated on each card; this view installs nothing.',
          style: TextStyle(fontSize: 12.5, color: t.inkMuted, height: 1.4),
        ),
      ]),
    );
  }
}

Iterable<MapEntry<String, int>> _statusEntries(Map<String, int> counts) sync* {
  const order = ['live', 'declared', 'missing', 'stale'];
  for (final key in order) {
    if (counts.containsKey(key)) yield MapEntry(key, counts[key] ?? 0);
  }
  for (final entry in counts.entries) {
    if (!order.contains(entry.key)) yield entry;
  }
}

class LaneRosterPanel extends StatelessWidget {
  final List<Lane> lanes;
  final void Function(String name)? onCheck;

  /// With a client, each card mounts its lane console. A lane this build
  /// holds back gets none: it has no tool to list.
  final GatewayClient? client;
  const LaneRosterPanel(
      {super.key, required this.lanes, this.onCheck, this.client});

  @override
  Widget build(BuildContext context) {
    if (lanes.isEmpty) {
      return const HonestNull('No lanes are declared in the current roster.');
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const Kicker('details'),
      const SizedBox(height: FwLayout.s2),
      for (final lane in lanes) ...[
        LaneCard(
          lane: lane,
          onCheck: onCheck,
          console: client == null || isLaneHeld(lane)
              ? null
              : LaneConsole(
                  key: ValueKey('console-${lane.name}'),
                  client: client!,
                  lane: lane,
                  onCheck: onCheck),
        ),
        const SizedBox(height: FwLayout.s2),
      ],
    ]);
  }
}

/// The tier every lane tool costs, folded under the cards. Runs happen in
/// each card's console; this lists what a call demands.
class AdvancedLaneTools extends StatelessWidget {
  final GatewayClient client;
  final bool alive;
  const AdvancedLaneTools(
      {super.key, required this.client, required this.alive});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      padding: EdgeInsets.zero,
      child: Material(
        color: Colors.transparent,
        child: ExpansionTile(
          tilePadding: const EdgeInsets.symmetric(
              horizontal: FwLayout.s4, vertical: FwLayout.s2),
          childrenPadding: const EdgeInsets.fromLTRB(
              FwLayout.s4, 0, FwLayout.s4, FwLayout.s4),
          title: const Text('Lane tool tiers'),
          subtitle: Text(
            'The tier each lane tool needs before it runs. Open a lane '
            'above to run its tools.',
            style: TextStyle(fontSize: 12.5, color: t.inkMuted),
          ),
          children: [
            CallableLanesPanel(client: client, alive: alive),
          ],
        ),
      ),
    );
  }
}
