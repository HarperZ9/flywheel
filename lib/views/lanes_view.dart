// lanes_view.dart — the Lanes view: a native sidebar list of Flywheel's 7 lanes
// with live health indicators.

import 'package:flutter/material.dart';
import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';

class LanesView extends StatelessWidget {
  final LaneRoster? roster;
  final VoidCallback? onProbe;

  const LanesView({super.key, this.roster, this.onProbe});

  @override
  Widget build(BuildContext context) {
    if (roster == null) {
      return const Center(child: CircularProgressIndicator());
    }
    final lanes = roster!.lanes;
    final by = roster!.byStatus;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Text('Lanes — ${roster!.nLanes}',
                  style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(width: 12),
              _statusChip('live', by['live'] ?? 0, FlywheelColors.live),
              const SizedBox(width: 6),
              _statusChip('declared', by['declared'] ?? 0, FlywheelColors.declared),
              const SizedBox(width: 6),
              _statusChip('missing', by['missing'] ?? 0, FlywheelColors.missing),
              const Spacer(),
              if (onProbe != null)
                FilledButton.tonal(
                  onPressed: onProbe,
                  child: const Text('Probe now'),
                ),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: ListView.builder(
            itemCount: lanes.length,
            itemBuilder: (ctx, i) => _laneTile(context, lanes[i]),
          ),
        ),
      ],
    );
  }

  Widget _laneTile(BuildContext context, Lane lane) {
    final color = laneStatusColor(lane.status);
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: color.withValues(alpha: 0.15),
          child: Icon(Icons.circle, color: color, size: 12),
        ),
        title: Text(lane.name, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text('${lane.organ} · ${lane.role}',
            style: Theme.of(context).textTheme.bodySmall),
        trailing: Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(lane.status.toUpperCase(),
                style: TextStyle(
                    color: color,
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    fontFamily: 'monospace')),
            Text(lane.installedVersion ?? lane.expectedVersion,
                style: Theme.of(context).textTheme.labelSmall),
          ],
        ),
        isThreeLine: true,
      ),
    );
  }

  Widget _statusChip(String label, int count, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Text('$count $label',
          style: TextStyle(
              color: color, fontSize: 11, fontWeight: FontWeight.w500)),
    );
  }
}
