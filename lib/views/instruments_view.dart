// instruments_view.dart -- the evaluation-engineering register, rendered.
// Every instrument reports from its live receipt; absence reads absent,
// never fabricated. If the instruments rot, this view says so.

import 'dart:convert';

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

/// The instruments that name a runnable route. Absence is honest: an
/// instrument without a live route gets no run affordance.
const _runRoutes = <String, (String, String)>{
  'uplift_lanes': ('GET', '/api/uplift'),
  'tension_ledger': ('GET', '/api/tension'),
  'robustness': ('POST', '/api/robustness/inject'),
  'admission_gates': ('GET', '/api/readiness'),
};

class _InstrumentsViewState extends State<InstrumentsView> {
  Map<String, dynamic>? _doc;
  String? _error;
  bool _loading = false;

  Future<void> _run(String name) async {
    final spec = _runRoutes[name];
    if (spec == null) return;
    final t = context.fw;
    Map<String, dynamic> doc;
    try {
      doc = spec.$1 == 'GET'
          ? await widget.client.getJson(spec.$2)
          : await widget.client.postJson(spec.$2, {});
    } catch (e) {
      doc = {'error': '$e'};
    }
    if (!mounted) return;
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: t.ground,
      builder: (ctx) => SizedBox(
        height: MediaQuery.of(ctx).size.height * 0.6,
        child: Padding(
          padding: const EdgeInsets.all(FwLayout.s5),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Kicker('$name · ${spec.$1} ${spec.$2}'),
            const SizedBox(height: FwLayout.s3),
            Expanded(
              child: SingleChildScrollView(
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: SelectableText(
                      const JsonEncoder.withIndent('  ').convert(doc),
                      style: fwMono(t, size: 11).copyWith(height: 1.5)),
                ),
              ),
            ),
          ]),
        ),
      ),
    );
  }

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
    final t = context.fw;
    return Column(children: [
      Container(
        padding: const EdgeInsets.symmetric(
            horizontal: FwLayout.s5, vertical: FwLayout.s3),
        decoration:
            BoxDecoration(border: Border(bottom: BorderSide(color: t.hairline))),
        child: Row(children: [
          Text('Instruments', style: Theme.of(context).textTheme.titleMedium),
          const Spacer(),
          if (_loading)
            SizedBox(
                width: 12,
                height: 12,
                child: CircularProgressIndicator(
                    strokeWidth: 1.6, color: t.inkFaint))
          else
            TextButton.icon(
              onPressed: () {
                setState(() => _error = null);
                _load();
              },
              icon: const Icon(Icons.refresh_rounded, size: 15),
              label: const Text('Re-read'),
            ),
        ]),
      ),
      Expanded(
        child: _error != null
            ? FwEmpty('Register unavailable: $_error')
            : _doc == null
                ? const Center(
                    child: SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2)))
                : SingleChildScrollView(
                    padding: const EdgeInsets.all(FwLayout.s5),
                    child: InstrumentList(_doc!, onRun: _run),
                  ),
      ),
    ]);
  }
}

/// Pure renderer for the register document; testable without a gateway.
class InstrumentList extends StatelessWidget {
  final Map<String, dynamic> doc;
  final ValueChanged<String>? onRun;
  const InstrumentList(this.doc, {super.key, this.onRun});

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
                    const Spacer(),
                    if (onRun != null &&
                        _runRoutes.containsKey('${r['name']}'))
                      TextButton(
                          onPressed: () => onRun!('${r['name']}'),
                          child: Text(
                              'run ${_runRoutes['${r['name']}']!.$2}',
                              style: fwMono(t, size: 10.5))),
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
