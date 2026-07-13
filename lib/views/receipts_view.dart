// receipts_view.dart — the Receipts view: the ledger of re-checkable
// artifacts. Two registers: the in-repo catalog (the files that define the
// world state, re-hashed on every read) and the proof envelopes the loop
// writes when verified work is accepted. No receipt, no accept.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class ReceiptsView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const ReceiptsView({super.key, required this.client, required this.alive});

  @override
  State<ReceiptsView> createState() => _ReceiptsViewState();
}

class _ReceiptsViewState extends State<ReceiptsView> {
  ReceiptsLedger? _ledger;
  String? _error;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(ReceiptsView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  Future<void> _load() async {
    if (!widget.alive) return;
    setState(() => _loading = true);
    try {
      final ledger = await widget.client.receipts();
      if (mounted) {
        setState(() {
          _ledger = ledger;
          _error = null;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = '$e';
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. The receipts ledger appears when it runs.',
          command: 'flywheel up');
    }
    if (_error != null) {
      return FwEmpty('The ledger could not be read: $_error');
    }
    if (_ledger == null) {
      return const Center(child: CircularProgressIndicator(strokeWidth: 2));
    }
    final l = _ledger!;
    final t = context.fw;
    return ViewScroll(
      children: [
        SectionHeader(
          'Receipts',
          kicker: 'no receipt, no accept',
          trailing: OutlinedButton(
            onPressed: _loading ? null : _load,
            child: Text(_loading ? 'Reading…' : 'Re-read'),
          ),
        ),
        const SizedBox(height: FwLayout.s4),
        Row(
          children: [
            Expanded(
                child: StatTile(
                    label: 'catalog present',
                    value: '${l.catalogPresent}/${l.catalog.length}',
                    status: l.catalogPresent == l.catalog.length
                        ? 'verified'
                        : 'drift')),
            const SizedBox(width: FwLayout.s3),
            Expanded(
                child: StatTile(
                    label: 'envelopes', value: '${l.envelopeCount}')),
            const SizedBox(width: FwLayout.s3),
            Expanded(
                child: StatTile(
                    label: 'accepted pass',
                    value: '${l.passCount}',
                    status: 'verified')),
          ],
        ),
        const SizedBox(height: FwLayout.s5),
        const Kicker('catalog · in-repo artifacts, re-hashed on every read',
            hot: true),
        const SizedBox(height: FwLayout.s3),
        HairlineCard(
          padding: const EdgeInsets.symmetric(
              horizontal: FwLayout.s4, vertical: FwLayout.s2),
          child: Column(
            children: [for (final r in l.catalog) _catalogRow(t, r)],
          ),
        ),
        const SizedBox(height: FwLayout.s5),
        const Kicker('envelopes · proof of accepted verified work'),
        const SizedBox(height: FwLayout.s3),
        if (l.envelopes.isEmpty)
          const HonestNull(
              'No proof envelopes in this run root yet. They appear when the '
              'loop accepts verified work; nothing is claimed until then.')
        else
          HairlineCard(
            padding: const EdgeInsets.symmetric(
                horizontal: FwLayout.s4, vertical: FwLayout.s2),
            child: Column(
              children: [for (final e in l.envelopes) _envelopeRow(t, e)],
            ),
          ),
      ],
    );
  }

  Widget _catalogRow(FwTokens t, CatalogReceipt r) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: FwLayout.s2 + 2),
      decoration: BoxDecoration(
          border: Border(bottom: BorderSide(color: t.hairline))),
      child: Row(
        children: [
          VerdictDot(r.present ? 'present' : 'absent', size: 7),
          const SizedBox(width: FwLayout.s3),
          Expanded(child: Text(r.path, style: fwMono(t, size: 12))),
          if (r.size != null)
            Text(_fmtSize(r.size!),
                style: fwMono(t, size: 11, color: t.inkFaint)),
          const SizedBox(width: FwLayout.s4),
          SizedBox(
            width: 110,
            child: Text(
                r.present
                    ? r.sha256.substring(0, 12.clamp(0, r.sha256.length))
                    : 'absent',
                textAlign: TextAlign.right,
                style: fwMono(t,
                    size: 11,
                    color: r.present ? t.inkMuted : t.unverifiable)),
          ),
        ],
      ),
    );
  }

  Widget _envelopeRow(FwTokens t, EnvelopeReceipt e) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: FwLayout.s2 + 2),
      decoration: BoxDecoration(
          border: Border(bottom: BorderSide(color: t.hairline))),
      child: Row(
        children: [
          VerdictPill(e.verdict,
              status: e.verdict == 'PASS' ? 'verified' : 'drift'),
          const SizedBox(width: FwLayout.s3),
          Expanded(child: Text(e.name, style: fwMono(t, size: 12))),
          if (e.taskId.isNotEmpty)
            Text(e.taskId, style: fwMono(t, size: 11, color: t.inkMuted)),
          const SizedBox(width: FwLayout.s4),
          Text(e.sha256.substring(0, 12.clamp(0, e.sha256.length)),
              style: fwMono(t, size: 11, color: t.inkFaint)),
        ],
      ),
    );
  }

  static String _fmtSize(int bytes) {
    if (bytes >= 1048576) {
      return '${(bytes / 1048576).toStringAsFixed(1)} MB';
    }
    if (bytes >= 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '$bytes B';
  }
}
