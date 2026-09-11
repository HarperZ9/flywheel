// lanes_view.dart — the Tools view: installed/readiness truth for every lane.
//
// The gateway owns lane state. This surface reads the roster, probes on user
// request, and keeps executable lane calls behind the existing grant-bound
// advanced panel. It intentionally does not expose the unpinned install helper
// as a public repair path.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../models/lane_readiness.dart';
import '../widgets/fw.dart';
import '../widgets/lane_health_panel.dart';

export '../widgets/lane_health_panel.dart' show LaneCard;

class LanesView extends StatelessWidget {
  final LaneRoster? roster;
  final bool alive;
  final VoidCallback? onProbe;

  /// Preserved for shell compatibility while the public Tools surface stops
  /// offering unreviewed per-lane install actions.
  final Future<Map<String, dynamic>> Function(String name)? onInstall;

  /// Needed for the callable list, which answers a different question from
  /// the roster: not what is installed, but what may be invoked and at what
  /// governance tier. Optional so a caller with no client still renders.
  final GatewayClient? client;

  const LanesView({
    super.key,
    this.roster,
    required this.alive,
    this.onProbe,
    this.onInstall,
    this.client,
  });

  @override
  Widget build(BuildContext context) {
    if (!alive) {
      return const FwEmpty(
        'The engine is offline. Tools appear when it runs.',
        command: 'flywheel up',
      );
    }
    if (roster == null) {
      return const Center(child: CircularProgressIndicator(strokeWidth: 2));
    }
    final lanes = [...roster!.lanes]..sort(_laneSort);
    final by = roster!.byStatus;
    final readiness =
        laneReadinessDetail(roster!.nLanes, by, probeRequested: true);
    return ViewScroll(
      storageKey: 'tools-lanes-view',
      children: [
        SectionHeader(
          'Tools',
          kicker: 'lane readiness',
          trailing: OutlinedButton(
            onPressed: onProbe,
            child: const Text('Probe now'),
          ),
        ),
        const SizedBox(height: FwLayout.s3),
        LaneReadinessPanel(
            total: roster!.nLanes, counts: by, detail: readiness),
        const SizedBox(height: FwLayout.s4),
        LaneRosterPanel(lanes: lanes),
        if (client != null) ...[
          const SizedBox(height: FwLayout.s4),
          AdvancedLaneTools(client: client!, alive: alive),
        ],
      ],
    );
  }
}

int _laneSort(Lane a, Lane b) {
  final byStatus = _statusRank(a.status).compareTo(_statusRank(b.status));
  if (byStatus != 0) return byStatus;
  return a.name.compareTo(b.name);
}

int _statusRank(String status) => switch (status) {
      'live' => 0,
      'declared' => 1,
      'stale' => 2,
      'missing' => 3,
      _ => 4,
    };
