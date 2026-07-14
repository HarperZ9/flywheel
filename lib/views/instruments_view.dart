// instruments_view.dart -- the evaluation-engineering register, rendered.
// Every instrument reports from its live receipt; absence reads absent,
// never fabricated. If the instruments rot, this view says so.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class InstrumentsView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const InstrumentsView(
      {super.key, required this.client, required this.alive});

  @override
  State<InstrumentsView> createState() => _InstrumentsViewState();
}

class _InstrumentsViewState extends State<InstrumentsView> {
  Map<String, dynamic>? _doc;
  String? _error;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (!widget.alive || _loading) return;
    setState(() => _loading = true);
    try {
      final doc = await widget.client.instruments();
      if (mounted) setState(() => _doc = doc);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. The register appears when it runs.',
          command: 'flywheel up');
    }
    if (_error != null) return FwEmpty('Register unavailable: $_error');
    if (_doc == null) return const Center(child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)));
    return SingleChildScrollView(
      padding: const EdgeInsets.all(FwLayout.s5),
      child: InstrumentList(_doc!),
    );
  }
}

/// Pure renderer for the register document; testable without a gateway.
class InstrumentList extends StatelessWidget {
  final Map<String, dynamic> doc;
  const InstrumentList(this.doc, {super.key});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final rows = ((doc['instruments'] ?? []) as List)
        .whereType<Map<String, dynamic>>()
        .toList();
    final present = doc['present_count'] ?? 0;
    final total = doc['total'] ?? rows.length;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker('evaluation engineering'),
        const SizedBox(height: FwLayout.s2),
        Row(children: [
          VerdictPill('$present/$total live',
              status: (total is int && total > 0 && present == total)
                  ? 'verified'
                  : (total == 0 ? 'unverifiable' : 'drift')),
        ]),
        const SizedBox(height: FwLayout.s4),
        for (final r in rows)
          Padding(
            padding: const EdgeInsets.only(bottom: FwLayout.s3),
            child: HairlineCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    VerdictDot((r['present'] ?? false) == true
                        ? 'verified'
                        : 'unverifiable'),
                    const SizedBox(width: FwLayout.s2),
                    Text('${r['name'] ?? ''}',
                        style: fwMono(t, size: 12)
                            .copyWith(color: t.ink)),
                  ]),
                  const SizedBox(height: FwLayout.s2),
                  Text('${r['summary'] ?? ''}',
                      style:
                          fwMono(t, size: 11.5).copyWith(color: t.inkSoft)),
                  if ('${r['receipt'] ?? ''}'.isNotEmpty) ...[
                    const SizedBox(height: FwLayout.s2),
                    HashText('receipt', '${r['receipt']}', keep: 48),
                  ],
                ],
              ),
            ),
          ),
        if ('${doc['note'] ?? ''}'.isNotEmpty) HonestNull('${doc['note']}'),
      ],
    );
  }
}
