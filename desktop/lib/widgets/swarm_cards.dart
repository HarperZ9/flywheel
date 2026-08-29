import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

String swarmPillStatus(String status) {
  switch (status) {
    case 'completed':
    case 'satisfied':
    case 'sealed':
      return 'verified';
    case 'running':
    case 'detached':
    case 'pending':
    case 'timeout':
      return 'pending';
    default:
      return 'drift';
  }
}

Map<String, dynamic> asSwarmMap(Map<dynamic, dynamic> m) =>
    m.map((k, v) => MapEntry(k.toString(), v));

class SwarmRowTile extends StatelessWidget {
  final Map<String, dynamic> row;
  final bool busy;
  final ValueChanged<Map<String, dynamic>> onOpen;
  final ValueChanged<String> onCancel;
  const SwarmRowTile({
    super.key,
    required this.row,
    required this.busy,
    required this.onOpen,
    required this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    final id = row['swarm_id'] ?? '';
    final status = (row['status'] ?? 'unknown').toString();
    final verdict = row['verdict'];
    final done = row['completed'];
    final total = row['total'] ?? row['children'];
    final cancellable = status == 'running' || status == 'detached';
    return Padding(
      padding: const EdgeInsets.all(FwLayout.s3),
      child:
          Row(children: [
        Expanded(
          child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                HashText('Swarm', id.toString()),
                const SizedBox(height: FwLayout.s1),
                Wrap(spacing: FwLayout.s2, crossAxisAlignment:
                    WrapCrossAlignment.center, children: [
                  VerdictPill(status, status: swarmPillStatus(status)),
                  if (verdict is String)
                    VerdictPill(verdict,
                        status:
                            verdict == 'satisfied' ? 'verified' : 'pending'),
                  if (done is int && total is int)
                    Text('$done of $total children completed',
                        style: const TextStyle(fontSize: 12))
                  else if (total is int)
                    Text('$total children',
                        style: const TextStyle(fontSize: 12)),
                ]),
              ]),
        ),
        TextButton(
            key: Key('swarm-open-$id'),
            onPressed: busy ? null : () => onOpen(row),
            child: const Text('Receipts')),
        if (cancellable)
          TextButton(
              key: Key('swarm-cancel-$id'),
              onPressed: busy ? null : () => onCancel(id as String),
              child: const Text('Cancel')),
      ]),
    );
  }
}

class SwarmDetailCard extends StatelessWidget {
  final Map<String, dynamic> snap;
  const SwarmDetailCard({super.key, required this.snap});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final receipt = snap['receipt'];
    final children = receipt is Map && receipt['children'] is List
        ? (receipt['children'] as List).whereType<Map>().map(asSwarmMap).toList()
        : <Map<String, dynamic>>[];
    return Padding(
      padding: const EdgeInsets.all(FwLayout.s3),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Swarm ${snap['swarm_id']}',
            style: TextStyle(
                fontSize: 13,
                color: t.ink,
                fontWeight: FontWeight.w600)),
        const SizedBox(height: FwLayout.s2),
        if (children.isEmpty)
          const HonestNull('No child receipts yet; the swarm is still running.')
        else
          ...children.map((c) => Padding(
                padding: const EdgeInsets.only(bottom: FwLayout.s1),
                child: Row(children: [
                  VerdictDot(swarmPillStatus('${c['status']}')),
                  const SizedBox(width: FwLayout.s2),
                  Expanded(
                      child: Text('${c['role']} ${c['child_id']}',
                          style:
                              TextStyle(fontSize: 12, color: t.inkSoft))),
                  Text('${c['status']}',
                      style: TextStyle(fontSize: 12, color: t.inkMuted)),
                ]),
              )),
      ]),
    );
  }
}
