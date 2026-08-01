// turn_receipt.dart — one chat turn's receipt, opened from the quiet
// verified mark. Everything renders as-is from the receipt the engine
// minted: the routing facts, the four hashes the id recomputes from, a
// served-model swap when the provider answered with something else, and
// the failover history when providers were skipped. The client computes
// nothing and hides nothing.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class TurnReceiptCard extends StatelessWidget {
  final Map<String, dynamic> receipt;
  const TurnReceiptCard({super.key, required this.receipt});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final served = '${receipt['served_model'] ?? ''}';
    final failover = (receipt['failover_from'] is List)
        ? (receipt['failover_from'] as List).map((e) => '$e').toList()
        : const <String>[];
    return HairlineCard(
      recessed: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('turn receipt'),
          const SizedBox(height: FwLayout.s2),
          if (receipt['routed_via'] != null)
            _fact(t, 'routed via', '${receipt['routed_via']}'),
          if (receipt['model_ref'] != null)
            _fact(t, 'model', '${receipt['model_ref']}'),
          // the provider answered with a different model than the receipt's
          // requested identity: the swap is named, never smoothed over
          if (served.isNotEmpty) _fact(t, 'served', served),
          if (receipt['seed'] != null) _fact(t, 'seed', '${receipt['seed']}'),
          const SizedBox(height: FwLayout.s2),
          for (final (label, key) in [
            ('receipt', 'receipt_id'),
            ('request', 'request_hash'),
            ('prompt', 'prompt_hash'),
            ('response', 'response_hash'),
          ])
            if ('${receipt[key] ?? ''}'.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: HashText(label, '${receipt[key]}', linkToReceipts: true),
              ),
          if (failover.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s2),
            Text('failed over from: ${failover.join('; ')}',
                style: fwMono(t, size: 10.5, color: t.inkMuted)),
          ],
          const SizedBox(height: FwLayout.s2),
          Text(
              'content-addressed: the same request and response recompute '
              'the same id, so anyone holding this turn can re-check it.',
              style: TextStyle(fontSize: 11, color: t.inkFaint, height: 1.4)),
        ],
      ),
    );
  }

  Widget _fact(FwTokens t, String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 1),
        child: Row(children: [
          SizedBox(
              width: 76,
              child:
                  Text(label, style: fwMono(t, size: 10.5, color: t.inkFaint))),
          Expanded(child: SelectableText(value, style: fwMono(t, size: 11.5))),
        ]),
      );
}
