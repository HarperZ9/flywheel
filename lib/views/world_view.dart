// world_view.dart — the World view: the projected, root-hashed state both
// person and model read. The root hash is the receipt: tamper any cataloged
// artifact and it moves. Findings render as a receipt-bound table with a
// verdict strip; the spine shows the flagship composition.

import 'package:flutter/material.dart';

import '../models/gateway_models.dart';
import '../models/render_status.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class WorldView extends StatelessWidget {
  final WorldDoc? world;
  final bool alive;

  const WorldView({super.key, this.world, required this.alive});

  @override
  Widget build(BuildContext context) {
    if (!alive) {
      return const FwEmpty(
          'The engine is offline. The projected world appears when it runs.',
          command: 'flywheel up');
    }
    if (world == null) {
      return const Center(child: CircularProgressIndicator(strokeWidth: 2));
    }
    final w = world!;
    final t = context.fw;
    final items = (w.findings['items'] is List)
        ? List<Map<String, dynamic>>.from(
            (w.findings['items'] as List).whereType<Map<String, dynamic>>())
        : <Map<String, dynamic>>[];
    return ViewScroll(
      children: [
        const SectionHeader('World', kicker: 'the projected state'),
        const SizedBox(height: FwLayout.s4),
        _rootCard(context, w),
        const SizedBox(height: FwLayout.s3),
        AdaptiveTiles(
          children: [
            StatTile(
                label: 'measured',
                value: '${w.findings['measured'] ?? 0}',
                status: countStatus(
                    int.tryParse('${w.findings['measured'] ?? 0}') ?? 0)),
            StatTile(
                label: 'pending',
                value: '${w.findings['pending'] ?? 0}',
                status: 'pending'),
            StatTile(
                label: 'spine',
                value: (w.spine?.closed ?? false) ? 'closed' : 'open',
                status: (w.spine?.closed ?? false) ? 'verified' : 'missing'),
          ],
        ),
        if (items.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s5),
          Row(children: [
            const Kicker('findings', hot: true),
            const SizedBox(width: FwLayout.s3),
            Expanded(child: _FindingsStrip(items: items)),
          ]),
          const SizedBox(height: FwLayout.s3),
          HairlineCard(
            padding: const EdgeInsets.symmetric(
                horizontal: FwLayout.s4, vertical: FwLayout.s2),
            child: Column(
              children: [
                for (final f in items) _findingRow(context, f),
              ],
            ),
          ),
        ],
        if (w.spine != null) ...[
          const SizedBox(height: FwLayout.s5),
          Kicker('spine · reconciler: ${w.spine!.reconciler}'),
          const SizedBox(height: FwLayout.s3),
          HairlineCard(
            padding: const EdgeInsets.symmetric(
                horizontal: FwLayout.s4, vertical: FwLayout.s3),
            child: Column(
              children: [
                for (final e in w.spine!.organs.entries)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 3),
                    child: Row(
                      children: [
                        SizedBox(
                            width: 130,
                            child: Text(e.key,
                                style: fwMono(t,
                                    size: 11.5, color: t.inkFaint))),
                        Expanded(
                          child: Text(
                              '${e.value} → ${w.spine!.routes[e.value] ?? e.value}',
                              style: fwMono(t, size: 12)),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
        if (w.cursor['present'] == true) ...[
          const SizedBox(height: FwLayout.s5),
          const Kicker('cursor'),
          const SizedBox(height: FwLayout.s3),
          HairlineCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${w.cursor['top_section'] ?? '(unknown)'}',
                    style: Theme.of(context).textTheme.bodyMedium),
                const SizedBox(height: FwLayout.s1),
                Text('updated ${w.cursor['last_updated'] ?? '?'}',
                    style: fwMono(t, size: 11, color: t.inkFaint)),
              ],
            ),
          ),
        ],
      ],
    );
  }

  Widget _rootCard(BuildContext context, WorldDoc w) {
    final t = context.fw;
    return HairlineCard(
      padding: const EdgeInsets.all(FwLayout.s5),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Projected world',
              style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: FwLayout.s3),
          HashText('root_hash', w.rootHash, keep: 40),
          if (w.merkleRoot != null) ...[
            const SizedBox(height: FwLayout.s1),
            HashText('merkle_root', w.merkleRoot!, keep: 40),
          ],
          const SizedBox(height: FwLayout.s3),
          Text(
              'Recomputed on every read. Tamper any cataloged receipt and '
              'this hash moves.',
              style: TextStyle(fontSize: 12, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s2),
          Text(w.schema, style: fwMono(t, size: 10.5, color: t.inkFaint)),
        ],
      ),
    );
  }

  Widget _findingRow(BuildContext context, Map<String, dynamic> f) {
    final t = context.fw;
    final status = '${f['status'] ?? 'pending'}';
    final verdict = status == 'measured' ? 'verified' : 'pending';
    final sha = f['source_sha256'];
    return Container(
      padding: const EdgeInsets.symmetric(vertical: FwLayout.s2 + 2),
      decoration: BoxDecoration(
          border: Border(bottom: BorderSide(color: t.hairline))),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: VerdictDot(verdict, size: 7),
          ),
          const SizedBox(width: FwLayout.s3),
          SizedBox(
            width: 170,
            child: Text('${f['key'] ?? ''}',
                style: fwMono(t, size: 11.5, color: t.inkSoft)),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                    f['value'] != null
                        ? '${f['value']}'
                        : '${f['claim'] ?? ''} (pending)',
                    style: TextStyle(fontSize: 12.5, color: t.inkSoft)),
                if ('${f['bounds'] ?? ''}'.isNotEmpty)
                  Text('${f['bounds']}',
                      style: TextStyle(fontSize: 11, color: t.inkFaint)),
              ],
            ),
          ),
          const SizedBox(width: FwLayout.s3),
          if (sha is String && sha.isNotEmpty)
            Text(sha.length > 12 ? sha.substring(0, 12) : sha,
                style: fwMono(t, size: 10.5, color: t.inkFaint)),
        ],
      ),
    );
  }
}

/// The findings strip: one square per finding, verdict-tinted. A chart in
/// the same hairline language as everything else.
class _FindingsStrip extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  const _FindingsStrip({required this.items});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Wrap(
      spacing: 3,
      runSpacing: 3,
      children: [
        for (final f in items)
          Container(
            width: 14,
            height: 14,
            decoration: BoxDecoration(
              color: (f['status'] == 'measured'
                      ? t.verified
                      : t.unverifiable)
                  .withValues(alpha: f['status'] == 'measured' ? 0.75 : 0.35),
              borderRadius: BorderRadius.circular(3),
              border: Border.all(color: t.line, width: 0.5),
            ),
          ),
      ],
    );
  }
}
