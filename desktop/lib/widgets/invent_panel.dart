// invent_panel.dart -- generation under witness.
//
// One round proposes conjectures the corpus does not already hold, hands
// every one to the kernel, and keeps only what the kernel accepts. The
// denominator is on screen: proposed, accepted, refused, declared, and the
// corpus size novelty is measured against. Novelty here means absent from
// this store, which is a smaller claim than it sounds and is stated as such.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'operation_grant_sheet.dart';

class InventPanel extends StatefulWidget {
  final GatewayClient client;
  const InventPanel({super.key, required this.client});

  @override
  State<InventPanel> createState() => _InventPanelState();
}

class _InventPanelState extends State<InventPanel> {
  final _k = TextEditingController(text: '12');
  final _offset = TextEditingController(text: '0');
  Map<String, dynamic>? _round;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _k.dispose();
    _offset.dispose();
    super.dispose();
  }

  Future<void> _run() async {
    if (_busy) return;
    final k = int.tryParse(_k.text.trim());
    final offset = int.tryParse(_offset.text.trim()) ?? 0;
    if (k == null || k < 1 || k > 50 || offset < 0) {
      setState(() => _error = "k must be 1..50 and offset non-negative");
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final requestId = 'invent-${DateTime.now().microsecondsSinceEpoch}';
      final r = await authorizeGatewayOperation<Map<String, dynamic>>(
        context,
        GatewayOperation.exact(
          action: 'invent.round',
          clientRequestId: requestId,
          operation: {'k': k, if (offset > 0) 'offset': offset},
        ),
        (body) => widget.client.postJson('/api/invent', body,
            timeout: const Duration(minutes: 10)),
        currentOperation: () => null,
      );
      if (mounted) setState(() => _round = r);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('conjecture forge · kept only if the kernel agrees'),
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            SizedBox(
              width: 110,
              child: TextField(
                controller: _k,
                enabled: !_busy,
                keyboardType: TextInputType.number,
                style: fwMono(t, size: 11.5, color: t.ink),
                decoration:
                    const InputDecoration(isDense: true, labelText: 'k'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            SizedBox(
              width: 110,
              child: TextField(
                controller: _offset,
                enabled: !_busy,
                keyboardType: TextInputType.number,
                style: fwMono(t, size: 11.5, color: t.ink),
                decoration:
                    const InputDecoration(isDense: true, labelText: 'offset'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            FilledButton(
              onPressed: _busy ? null : _run,
              child: Text(_busy ? 'Proposing…' : 'Run a round'),
            ),
          ]),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('The round did not run: $_error'),
          ],
          if (_round != null) ...[
            const SizedBox(height: FwLayout.s3),
            _roundBlock(t, _round!),
          ],
        ],
      ),
    );
  }

  Widget _roundBlock(FwTokens t, Map<String, dynamic> r) {
    final accepted = r['accepted'] is List ? (r['accepted'] as List) : const [];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
            'proposed ${r['proposed'] ?? '—'}  ·  accepted ${accepted.length}'
            '  ·  refused ${r['refused'] ?? '—'}  ·  declared '
            '${r['declared'] ?? '—'}  ·  corpus ${r['corpus_size'] ?? '—'}',
            style: fwMono(t, size: 11, color: t.inkFaint)),
        const SizedBox(height: FwLayout.s2),
        if (accepted.isEmpty)
          const HonestNull(
              'The kernel accepted none of them. A round that keeps nothing '
              'is the expected case, not a broken run.')
        else
          for (final item in accepted.whereType<Map>())
            Padding(
              padding: const EdgeInsets.only(bottom: FwLayout.s2),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SelectableText('${item['statement'] ?? ''}',
                      style: fwMono(t, size: 11, color: t.ink)),
                  const SizedBox(height: 3),
                  Row(children: [
                    Text('rung ${item['rung'] ?? '—'}',
                        style: fwMono(t, size: 10.5, color: t.inkFaint)),
                    const SizedBox(width: FwLayout.s3),
                    HashText(
                        'statement', '${item['statement_sha256'] ?? ''}',
                        keep: 12),
                  ]),
                ],
              ),
            ),
        if (r['note'] != null) ...[
          const SizedBox(height: FwLayout.s2),
          Text('${r['note']}',
              style: fwMono(t, size: 10.5, color: t.inkFaint)),
        ],
      ],
    );
  }
}
