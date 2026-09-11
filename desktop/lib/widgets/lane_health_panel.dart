// lane_health_panel.dart — compact lane readiness and details widgets for the
// public Tools surface. Rows show state and facts first; executable calls stay
// in the explicit advanced section.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../models/lane_identity.dart';
import '../theme/flywheel_theme.dart';
import 'callable_lanes_panel.dart';
import 'fw.dart';
import 'lane_call_panel.dart';

class LaneReadinessPanel extends StatelessWidget {
  final int total;
  final Map<String, int> counts;
  final String detail;
  const LaneReadinessPanel({
    super.key,
    required this.total,
    required this.counts,
    required this.detail,
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
            for (final entry in _statusEntries(counts))
              VerdictPill('${entry.value} ${entry.key}', status: entry.key),
          ],
        ),
        const SizedBox(height: FwLayout.s3),
        Text(
          'Probe checks the existing gateway lane roster. Setup and repair are '
          'reported as state here; this build exposes no unpinned install '
          'operation from the public Tools view.',
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
  const LaneRosterPanel({super.key, required this.lanes});

  @override
  Widget build(BuildContext context) {
    if (lanes.isEmpty) {
      return const HonestNull('No lanes are declared in the current roster.');
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const Kicker('details'),
      const SizedBox(height: FwLayout.s2),
      for (final lane in lanes) ...[
        LaneCard(lane: lane),
        const SizedBox(height: FwLayout.s2),
      ],
    ]);
  }
}

class LaneCard extends StatelessWidget {
  final Lane lane;
  final Future<Map<String, dynamic>> Function(String name)? onInstall;
  const LaneCard({super.key, required this.lane, this.onInstall});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final id = laneIdentities[lane.name];
    final title = id?.title ?? lane.name;
    final surface = id?.surface ?? 'runtime lane';
    final status = lane.status.isEmpty ? 'unknown' : lane.status;
    return HairlineCard(
      padding: EdgeInsets.zero,
      child: Material(
        color: Colors.transparent,
        child: Theme(
          data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
          child: ExpansionTile(
            tilePadding: const EdgeInsets.fromLTRB(
                FwLayout.s4, FwLayout.s3, FwLayout.s4, FwLayout.s2),
            childrenPadding: const EdgeInsets.fromLTRB(
                FwLayout.s4, 0, FwLayout.s4, FwLayout.s4),
            title: Row(children: [
              Expanded(
                child: Text(title,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 15.5, fontWeight: FontWeight.w700)),
              ),
              const SizedBox(width: FwLayout.s2),
              VerdictPill(status, status: status),
            ]),
            subtitle: Padding(
              padding: const EdgeInsets.only(top: FwLayout.s2),
              child: Wrap(
                  spacing: FwLayout.s3,
                  runSpacing: FwLayout.s1,
                  children: [
                    _Fact(label: 'surface', value: surface),
                    _Fact(label: 'version', value: _versionText(lane)),
                    _Fact(label: 'tools', value: _toolText(lane)),
                  ]),
            ),
            children: [
              _detailLine(
                  t,
                  'runtime',
                  lane.detail.isEmpty
                      ? 'No runtime detail reported.'
                      : lane.detail),
              _detailLine(t, 'state', _stateText(lane)),
              if (id != null) ...[
                _detailLine(t, 'role', '${lane.organ} · ${lane.role}'),
                _detailLine(t, 'identity', id.identity),
              ] else if (lane.organ.isNotEmpty || lane.role.isNotEmpty)
                _detailLine(t, 'role', '${lane.organ} · ${lane.role}'),
            ],
          ),
        ),
      ),
    );
  }

  String _versionText(Lane lane) {
    if (lane.installedVersion != null && lane.installedVersion!.isNotEmpty) {
      return lane.installedVersion!;
    }
    if (lane.expectedVersion.isNotEmpty) {
      return 'expects ${lane.expectedVersion}';
    }
    return lane.kind.isEmpty ? 'unknown' : lane.kind;
  }

  String _toolText(Lane lane) =>
      lane.tools == null ? 'not probed' : '${lane.tools} tools';

  String _stateText(Lane lane) {
    if (lane.isLive) {
      return 'Ready in the current roster. Use the advanced callable section '
          'only when a lane reports callable tools and the grant matches.';
    }
    if (lane.isDeclared) {
      return 'Declared by the registry, but not verified by a lane probe yet.';
    }
    if (lane.isMissing) {
      return 'Missing or blocked in this runtime. No reviewed native setup '
          'operation is exposed from this public view.';
    }
    if (lane.status == 'stale') {
      return 'Installed state differs from the expected version. No reviewed '
          'native repair operation is exposed from this public view.';
    }
    return 'The roster returned an unrecognized state: ${lane.status}.';
  }
}

class _Fact extends StatelessWidget {
  final String label;
  final String value;
  const _Fact({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Text('$label $value', style: fwMono(t, size: 11, color: t.inkFaint));
  }
}

Widget _detailLine(FwTokens t, String label, String value) => Padding(
      padding: const EdgeInsets.only(top: FwLayout.s2),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          width: 72,
          child: Text(label, style: fwMono(t, size: 11, color: t.inkFaint)),
        ),
        Expanded(
          child: Text(value,
              style: TextStyle(fontSize: 12.5, color: t.inkSoft, height: 1.4)),
        ),
      ]),
    );

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
          title: const Text('Advanced lane calls'),
          subtitle: Text(
            'Grant-bound callable tools and exact lane/tool execution.',
            style: TextStyle(fontSize: 12.5, color: t.inkMuted),
          ),
          children: [
            CallableLanesPanel(client: client, alive: alive),
            const SizedBox(height: FwLayout.s3),
            LaneCallPanel(client: client),
          ],
        ),
      ),
    );
  }
}
