// world_view.dart — the World view: the projected-world spine + root hash.
// This is the receipt-badge surface: the root hash is displayed prominently
// and can be re-verified client-side (Phase 2b adds the re-verify button).

import 'package:flutter/material.dart';
import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';

class WorldView extends StatelessWidget {
  final WorldDoc? world;

  const WorldView({super.key, this.world});

  @override
  Widget build(BuildContext context) {
    if (world == null) {
      return const Center(child: CircularProgressIndicator());
    }
    final spine = world!.spine;
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        // Root hash card — the prominent receipt
        Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  Icon(Icons.fingerprint,
                      color: FlywheelColors.match, size: 18),
                  const SizedBox(width: 8),
                  Text('Projected World',
                      style: Theme.of(context).textTheme.titleLarge),
                ]),
                const SizedBox(height: 12),
                _hashRow('root_hash', world!.rootHash),
                if (world!.merkleRoot != null)
                  _hashRow('merkle_root', world!.merkleRoot!),
                const SizedBox(height: 8),
                Text(world!.schema,
                    style: Theme.of(context).textTheme.labelSmall),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        // Spine
        if (spine != null) ...[
          Text('Spine — reconciler: ${spine.reconciler}',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  _spineRow(context, 'closed',
                      spine.closed ? 'CLOSED' : 'OPEN',
                      spine.closed ? FlywheelColors.match : FlywheelColors.missing),
                  const Divider(),
                  ...spine.organs.entries.map((e) => _spineRow(
                      context, e.key, '${e.value} → ${spine.routes[e.value] ?? e.value}',
                      FlywheelColors.drift)),
                ],
              ),
            ),
          ),
        ],
        const SizedBox(height: 16),
        // Findings summary
        if (world!.findings.isNotEmpty) ...[
          Text('Findings', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  _spineRow(context, 'measured',
                      '${world!.findings['measured'] ?? '?'}',
                      FlywheelColors.match),
                  _spineRow(context, 'pending',
                      '${world!.findings['pending'] ?? '?'}',
                      FlywheelColors.unverifiable),
                ],
              ),
            ),
          ),
        ],
        // Cursor
        if (world!.cursor.isNotEmpty && world!.cursor['present'] == true) ...[
          const SizedBox(height: 16),
          Text('Cursor', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                '${world!.cursor['top_section'] ?? '(unknown)'}\n'
                'updated: ${world!.cursor['last_updated'] ?? '?'}',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ),
          ),
        ],
      ],
    );
  }

  Widget _hashRow(String label, String hash) {
    final short = hash.length > 24 ? '${hash.substring(0, 24)}…' : hash;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Text('$label  ', style: const TextStyle(fontFamily: 'monospace', fontSize: 12)),
          SelectableText(short,
              style: const TextStyle(fontFamily: 'monospace', fontSize: 13, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }

  Widget _spineRow(BuildContext context, String label, String value, Color color) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          Text(label.padRight(12),
              style: TextStyle(
                  fontFamily: 'monospace', fontSize: 12, color: color)),
          const SizedBox(width: 8),
          Expanded(child: Text(value, style: TextStyle(fontSize: 13, color: color))),
        ],
      ),
    );
  }
}
