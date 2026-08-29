// audit_receipt_panel.dart — the receipt-chained post-work review, live on stage.
//
// Paste a sealed work receipt; RUN AUDIT reviews it and seals the judgment into
// an audit receipt CHAINED onto the work (prev_receipt_sha256 = the work's seal
// hex). VERIFY re-checks it (MATCH) and shows the chain link. CORRUPT ONE BYTE
// flips one hex char of a COPY — never the stored receipt — and verifies THAT:
// the same verifier refuses and NAMES the failing check. The review runs
// deterministically with no model (a narrator is an optional gateway feature).
import 'dart:convert';

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'receipt_verify_controls.dart';

class AuditReceiptPanel extends StatefulWidget {
  /// Runs the audit over a parsed work receipt → {reviews, verdict, confidence,
  /// summary, does_not_prove, receipt, ...} or {error}.
  final Future<Map<String, dynamic>> Function(Map<String, dynamic> workReceipt)
      onRun;

  /// Verifies an audit receipt offline, with the work receipt for the chain
  /// check → {verdict, failure_class, detail}.
  final Future<Map<String, dynamic>> Function(
      Map<String, dynamic> auditReceipt,
      Map<String, dynamic>? workReceipt) onVerify;

  const AuditReceiptPanel(
      {super.key, required this.onRun, required this.onVerify});

  @override
  State<AuditReceiptPanel> createState() => _AuditReceiptPanelState();
}

class _AuditReceiptPanelState extends State<AuditReceiptPanel> {
  final _workCtrl = TextEditingController();
  bool _running = false;
  bool _verifying = false;
  Map<String, dynamic>? _workReceipt; // the parsed work receipt (kept for chain)
  Map<String, dynamic>? _runDoc; // the sealed audit body
  String? _runError; // a parse or run error reason
  Map<String, dynamic>? _verifyDoc; // the VERIFY path (expects MATCH)
  Map<String, dynamic>? _corruptDoc; // the CORRUPT path (expects TAMPERED)

  @override
  void dispose() {
    _workCtrl.dispose();
    super.dispose();
  }

  Map<String, dynamic>? get _receipt {
    final r = _runDoc?['receipt'];
    return r is Map ? Map<String, dynamic>.from(r) : null;
  }

  Future<void> _run() async {
    if (_running) return;
    Map<String, dynamic> work;
    try {
      final parsed = jsonDecode(_workCtrl.text.trim());
      if (parsed is! Map) throw const FormatException('not a JSON object');
      work = Map<String, dynamic>.from(parsed);
    } catch (_) {
      setState(() => _runError =
          'the work receipt is not valid JSON. Paste a sealed receipt object.');
      return;
    }
    setState(() {
      _running = true;
      _runError = null;
      _verifyDoc = null;
      _corruptDoc = null;
      _workReceipt = work;
    });
    final r = await widget.onRun(work);
    if (!mounted) return;
    setState(() {
      _running = false;
      _runDoc = r['receipt'] is Map ? r : null;
      if (_runDoc == null) _runError = '${r['error'] ?? 'no receipt returned'}';
    });
  }

  Future<void> _check(bool corrupt) async {
    final receipt = _receipt;
    if (receipt == null || _verifying) return;
    // CORRUPT flips one hex char of a COPY, client-side; the stored receipt is
    // never touched — this proves the refusal without corrupting the record.
    final subject = corrupt ? flipOneHexChar(receipt) : receipt;
    setState(() => _verifying = true);
    final v = await widget.onVerify(subject, _workReceipt);
    if (!mounted) return;
    setState(() {
      _verifying = false;
      if (corrupt) {
        _corruptDoc = v;
      } else {
        _verifyDoc = v;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('work receipt'),
      const SizedBox(height: FwLayout.s3),
      _workField(t),
      const SizedBox(height: FwLayout.s3),
      FilledButton(
        onPressed: _running ? null : _run,
        child: Text(_running ? 'Reviewing…' : 'Run audit'),
      ),
      if (_runError != null) ...[
        const SizedBox(height: FwLayout.s3),
        HonestNull(_runError!),
      ],
      if (_runDoc == null && _runError == null && !_running)
        const Padding(
          padding: EdgeInsets.only(top: FwLayout.s3),
          child: HonestNull(
              'No audit yet. Paste a sealed work receipt and run the review; the '
              'judgment seals into a receipt chained onto that work.'),
        ),
      if (_runDoc != null) ...[
        const SizedBox(height: FwLayout.s4),
        _resultCard(t),
      ],
    ]);
  }

  Widget _workField(FwTokens t) {
    final border = OutlineInputBorder(
      borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
      borderSide: BorderSide(color: t.line),
    );
    return TextField(
      controller: _workCtrl,
      minLines: 3,
      maxLines: 6,
      enabled: !_running,
      style: fwMono(t, size: 11.5, color: t.inkSoft),
      decoration: InputDecoration(
        hintText: 'Paste a sealed work receipt (JSON) …',
        hintStyle: fwMono(t, size: 11.5, color: t.inkFaint),
        border: border,
        enabledBorder: border,
      ),
    );
  }

  Widget _resultCard(FwTokens t) {
    final reviews = (_runDoc?['reviews'] as List?) ?? const [];
    final verdict = '${_runDoc?['verdict'] ?? ''}';
    final confidence = '${_runDoc?['confidence'] ?? ''}';
    final dnp = '${_runDoc?['does_not_prove'] ?? ''}';
    final summary = '${_runDoc?['summary'] ?? ''}';
    final sealHex = '${(_receipt?['seal'] as Map?)?['hex'] ?? ''}';
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          VerdictDot(_verdictStatus(verdict), size: 8),
          const SizedBox(width: FwLayout.s2),
          VerdictPill(verdict.toLowerCase(), status: _verdictStatus(verdict)),
          const SizedBox(width: FwLayout.s2),
          Text('confidence $confidence',
              style: fwMono(t, size: 10.5, color: t.inkFaint)),
        ]),
        const SizedBox(height: FwLayout.s3),
        for (final r in reviews.whereType<Map>()) _reviewRow(t, r),
        if (summary.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          Text(summary,
              style: TextStyle(fontSize: 12, height: 1.45, color: t.inkSoft)),
        ],
        if (dnp.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull(dnp),
        ],
        const SizedBox(height: FwLayout.s3),
        Divider(height: 1, color: t.hairline),
        const SizedBox(height: FwLayout.s3),
        HashText('seal', sealHex, keep: 32),
        const SizedBox(height: FwLayout.s4),
        Wrap(spacing: FwLayout.s3, runSpacing: FwLayout.s2, children: [
          FilledButton.tonal(
            onPressed: _verifying ? null : () => _check(false),
            child: Text(_verifying ? 'Verifying…' : 'Verify'),
          ),
          OutlinedButton(
            onPressed: _verifying ? null : () => _check(true),
            child: const Text('Corrupt one byte'),
          ),
        ]),
        if (_verifyDoc != null) ...[
          const SizedBox(height: FwLayout.s3),
          VerifyStateRow(
            doc: _verifyDoc!,
            chainLabel: 'chain → work receipt',
            chainHash: '${_receipt?['prev_receipt_sha256'] ?? ''}',
          ),
        ],
        if (_corruptDoc != null) ...[
          const SizedBox(height: FwLayout.s3),
          TamperStateCard(doc: _corruptDoc!),
        ],
      ]),
    );
  }

  Widget _reviewRow(FwTokens t, Map r) => Padding(
        padding: const EdgeInsets.only(bottom: FwLayout.s2),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: VerdictDot(_severityStatus('${r['severity']}'), size: 7),
          ),
          const SizedBox(width: FwLayout.s2),
          SizedBox(
            width: 92,
            child: Text('${r['dimension'] ?? ''}',
                style: fwMono(t, size: 10.5, color: t.inkFaint)),
          ),
          Expanded(
            child: Text('${r['summary'] ?? ''}',
                style: fwMono(t, size: 11, color: t.inkSoft)),
          ),
        ]),
      );

  String _verdictStatus(String v) =>
      {'PASS': 'verified', 'FAIL': 'drift'}[v.toUpperCase()] ?? 'unverifiable';

  String _severityStatus(String s) =>
      {'INFO': 'verified', 'CRITICAL': 'drift'}[s.toUpperCase()] ??
      'unverifiable';
}
