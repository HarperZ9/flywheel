// usage_receipt_panel.dart — the signed spend of a session, on stage.
//
// Every routed answer seals a usage receipt binding the PROVIDER-REPORTED token
// counts (or a labeled estimate when the provider returned none) and the model
// reference. This panel reads the session roll-up, shows the total spend and a
// per-answer breakdown with each number's provenance (provider_reported /
// estimated / unpriced_local), and VERIFY re-checks one receipt offline — MATCH
// is the accept mark. The dollar figure is always a table lookup, never a
// provider-billed number, so it is labeled as such and never invented. Dumb
// widget: async callbacks in, no client, no network of its own.
import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class UsageReceiptPanel extends StatefulWidget {
  /// Loads the session summary -> {n, total_tokens, priced_total, unpriced_count,
  /// by_endpoint, receipts:[...]} or {error}.
  final Future<Map<String, dynamic>> Function() loadSummary;

  /// Re-checks one usage receipt offline -> {verdict, failure_class, detail}.
  final Future<Map<String, dynamic>> Function(Map<String, dynamic> receipt)
      onVerify;

  const UsageReceiptPanel(
      {super.key, required this.loadSummary, required this.onVerify});

  @override
  State<UsageReceiptPanel> createState() => _UsageReceiptPanelState();
}

class _UsageReceiptPanelState extends State<UsageReceiptPanel> {
  bool _loading = false;
  Map<String, dynamic>? _summary;
  String? _loadError;
  Map<String, dynamic>? _verifyDoc; // the offline verify result (expects MATCH)
  int? _verifiedIndex;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadError = null;
      _verifyDoc = null;
      _verifiedIndex = null;
    });
    final s = await widget.loadSummary();
    if (!mounted) return;
    setState(() {
      _loading = false;
      if (s['error'] != null) {
        _summary = null;
        _loadError = '${s['error']}';
      } else {
        _summary = s;
      }
    });
  }

  List<Map<String, dynamic>> get _receipts {
    final r = _summary?['receipts'];
    if (r is! List) return const [];
    return r.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
  }

  Future<void> _verify(Map<String, dynamic> receipt, int index) async {
    final v = await widget.onVerify(receipt);
    if (!mounted) return;
    setState(() {
      _verifyDoc = v;
      _verifiedIndex = index;
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final n = int.tryParse('${_summary?['n'] ?? 0}') ?? 0;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        const Kicker('usage metering'),
        const Spacer(),
        TextButton(
          onPressed: _loading ? null : _load,
          child: Text(_loading ? 'Reading…' : 'Refresh'),
        ),
      ]),
      const SizedBox(height: FwLayout.s3),
      if (_loadError != null)
        HonestNull('The engine is offline or returned no summary: $_loadError')
      else if (_loading && _summary == null)
        Text('reading receipts…',
            style: fwMono(t, size: 11.5, color: t.inkFaint))
      else if (n == 0)
        const HonestNull(
            'No usage receipts yet. Route an answer through any provider and its '
            'spend seals into a signed receipt you can verify offline.')
      else ...[
        _totals(t),
        const SizedBox(height: FwLayout.s4),
        _receiptList(t),
        if (_verifyDoc != null) ...[
          const SizedBox(height: FwLayout.s3),
          _verifyState(t, _verifyDoc!),
        ],
      ],
    ]);
  }

  Widget _totals(FwTokens t) {
    final tokens = (_summary?['total_tokens'] as Map?) ?? const {};
    final priced = (_summary?['priced_total'] as Map?) ?? const {};
    final amount = '${priced['amount'] ?? ''}';
    final currency = '${priced['currency'] ?? 'USD'}';
    final pricedLabel = amount.isEmpty ? 'none priced' : '$currency $amount';
    return AdaptiveTiles(children: [
      StatTile(label: 'total tokens', value: '${tokens['total'] ?? '0'}'),
      StatTile(
          label: 'priced total (table)',
          value: pricedLabel,
          status: amount.isEmpty ? null : 'verified'),
      StatTile(
          label: 'unpriced answers',
          value: '${_summary?['unpriced_count'] ?? '0'}'),
    ]);
  }

  Widget _receiptList(FwTokens t) {
    final receipts = _receipts;
    final shown = receipts.length > 12 ? receipts.sublist(0, 12) : receipts;
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        for (final (i, r) in shown.indexed) _receiptRow(t, r, i),
        if (receipts.length > shown.length) ...[
          const SizedBox(height: FwLayout.s2),
          Text('+ ${receipts.length - shown.length} more receipts',
              style: fwMono(t, size: 10.5, color: t.inkFaint)),
        ],
      ]),
    );
  }

  Widget _receiptRow(FwTokens t, Map<String, dynamic> r, int index) {
    final tokens = (r['tokens'] as Map?) ?? const {};
    final cost = (r['cost'] as Map?) ?? const {};
    final source = '${r['source'] ?? ''}';
    final amount = '${cost['amount'] ?? ''}';
    final currency = '${cost['currency'] ?? ''}';
    final endpoint = '${r['endpoint'] ?? ''}';
    final costLabel = amount.isEmpty ? 'no price' : '$currency $amount';
    final verified = _verifiedIndex == index;
    return InkWell(
      onTap: () => _verify(r, index),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: FwLayout.s2),
        child: Row(children: [
          VerdictDot(_sourceStatus(source), size: 7),
          const SizedBox(width: FwLayout.s2),
          Expanded(
            child: Text(endpoint.isEmpty ? '(unknown)' : endpoint,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: fwMono(t, size: 11.5, color: t.inkSoft)),
          ),
          Text('${tokens['total'] ?? '0'} tok',
              style: fwMono(t, size: 10.5, color: t.inkMuted)),
          const SizedBox(width: FwLayout.s3),
          SizedBox(
            width: 92,
            child: Text(costLabel,
                textAlign: TextAlign.right,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: fwMono(t, size: 10.5, color: t.inkMuted)),
          ),
          const SizedBox(width: FwLayout.s3),
          SizedBox(
            width: 118,
            child: Text(source,
                textAlign: TextAlign.right,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: fwMono(t, size: 10, color: t.inkFaint)),
          ),
          if (verified) ...[
            const SizedBox(width: FwLayout.s2),
            VerdictDot(_verifyStatus('${_verifyDoc?['verdict'] ?? ''}'), size: 8),
          ],
        ]),
      ),
    );
  }

  // The verify result: MATCH is the accept mark, TAMPERED the one hot mark. The
  // whole point of a signed receipt is that a stranger re-derives this offline.
  Widget _verifyState(FwTokens t, Map<String, dynamic> doc) {
    final verdict = '${doc['verdict'] ?? ''}';
    final status = _verifyStatus(verdict);
    return Row(children: [
      VerdictDot(status, size: 8),
      const SizedBox(width: FwLayout.s2),
      VerdictPill(verdict.toLowerCase(), status: status),
      const SizedBox(width: FwLayout.s2),
      Expanded(
        child: Text('${doc['detail'] ?? ''}',
            style: fwMono(t, size: 10.5, color: t.inkMuted)),
      ),
    ]);
  }

  String _sourceStatus(String source) => switch (source) {
        'provider_reported' => 'verified',
        _ => 'unverifiable', // estimated / unpriced_local are honest unknowns
      };

  String _verifyStatus(String verdict) => switch (verdict.toUpperCase()) {
        'MATCH' => 'verified',
        'TAMPERED' => 'drift',
        _ => 'unverifiable',
      };
}
