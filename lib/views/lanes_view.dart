// lanes_view.dart — the Lanes view: the flagship roster, each product
// presented in its own words with live health.
//
// Fast install-presence status comes with the ambient poll; "Probe" runs the
// real MCP handshake (user-triggered only; each probe spawns the lane's
// server process).

import 'package:flutter/material.dart';

import '../models/gateway_models.dart';
import '../models/lane_identity.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class LanesView extends StatelessWidget {
  final LaneRoster? roster;
  final bool alive;
  final VoidCallback? onProbe;

  const LanesView(
      {super.key, this.roster, required this.alive, this.onProbe});

  @override
  Widget build(BuildContext context) {
    if (!alive) {
      return const FwEmpty('The engine is offline. Lanes appear when it runs.',
          command: 'flywheel up');
    }
    if (roster == null) {
      return const Center(child: CircularProgressIndicator(strokeWidth: 2));
    }
    final lanes = roster!.lanes;
    final by = roster!.byStatus;
    return ViewScroll(
      children: [
        SectionHeader(
          'Lanes',
          kicker: 'one surface, every engine',
          trailing: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (final e in by.entries) ...[
                VerdictPill('${e.value} ${e.key}', status: e.key),
                const SizedBox(width: FwLayout.s2),
              ],
              const SizedBox(width: FwLayout.s2),
              OutlinedButton(
                  onPressed: onProbe, child: const Text('Probe now')),
            ],
          ),
        ),
        const SizedBox(height: FwLayout.s3),
        Text(
          'Each lane is a full product that also runs alone. Probing spawns '
          'its MCP server and calls its own status tool; the verdict below '
          'is the tool\'s answer, not an assumption.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: FwLayout.s5),
        LayoutBuilder(
          builder: (ctx, box) {
            final twoCol = box.maxWidth >= 880;
            return _laneGrid(lanes, twoCol);
          },
        ),
      ],
    );
  }

  Widget _laneGrid(List<Lane> lanes, bool twoCol) {
    if (!twoCol) {
      return Column(
        children: [
          for (final lane in lanes)
            Padding(
              padding: const EdgeInsets.only(bottom: FwLayout.s3),
              child: LaneCard(lane: lane),
            ),
        ],
      );
    }
    final rows = <Widget>[];
    for (var i = 0; i < lanes.length; i += 2) {
      rows.add(Padding(
        padding: const EdgeInsets.only(bottom: FwLayout.s3),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(child: LaneCard(lane: lanes[i])),
            const SizedBox(width: FwLayout.s3),
            Expanded(
              child: i + 1 < lanes.length
                  ? LaneCard(lane: lanes[i + 1])
                  : const SizedBox(),
            ),
          ],
        ),
      ));
    }
    return Column(children: rows);
  }
}

class LaneCard extends StatelessWidget {
  final Lane lane;
  const LaneCard({super.key, required this.lane});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final id = laneIdentities[lane.name];
    final title = id?.title ?? lane.name;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(title,
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.w700)),
              ),
              VerdictPill(lane.status, status: lane.status),
            ],
          ),
          const SizedBox(height: FwLayout.s1),
          Kicker('${lane.organ} · ${lane.role}'),
          const SizedBox(height: FwLayout.s3),
          Text(
            id?.identity ?? lane.detail,
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: FwLayout.s3),
          Row(
            children: [
              Text(lane.installedVersion ?? lane.expectedVersion,
                  style: fwMono(t, size: 11, color: t.inkFaint)),
              if (lane.tools != null) ...[
                const SizedBox(width: FwLayout.s3),
                Text('${lane.tools} tools',
                    style: fwMono(t, size: 11, color: t.inkFaint)),
              ],
              const Spacer(),
              if (id != null)
                Text(id.surface,
                    style: fwMono(t, size: 11, color: t.inkMuted)),
            ],
          ),
          if (lane.detail.isNotEmpty && id != null) ...[
            const SizedBox(height: FwLayout.s2),
            Text(lane.detail,
                style: TextStyle(fontSize: 11.5, color: t.inkFaint)),
          ],
        ],
      ),
    );
  }
}
