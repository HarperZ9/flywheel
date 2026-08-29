// eval_receipt_panel.dart — the signed eval-run receipt, live on stage.
//
// A real eval seals its outcome into a receipt binding endpoint, model, dataset
// digest, config, and judge. VERIFY re-checks it (MATCH). CORRUPT ONE BYTE flips
// one hex char of a COPY — never the stored receipt — and verifies THAT: the
// same verifier now refuses and NAMES the failing check. The refusal is a
// first-class visual state. Dumb widget: async callbacks in, no client.
import 'package:flutter/material.dart';

import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'model_picker.dart';
import 'receipt_verify_controls.dart';
import 'model_selector.dart';

class EvalReceiptPanel extends StatefulWidget {
  final List<EndpointRow> endpoints;

  /// The chosen endpoint (null before one is picked) and its model override
  /// (null/empty means the endpoint default).
  final String? endpoint;
  final String? model;
  final ValueChanged<String> onEndpoint;
  final ValueChanged<String> onModel;
  final Future<Map<String, dynamic>> Function() loadModels;

  /// Runs the eval -> {results, receipt, receipt_file, model_ref} or {error}.
  final Future<Map<String, dynamic>> Function() onRun;

  /// Verifies a receipt offline -> {verdict, failure_class, detail}.
  final Future<Map<String, dynamic>> Function(Map<String, dynamic> receipt)
      onVerify;

  const EvalReceiptPanel({
    super.key,
    required this.endpoints,
    required this.endpoint,
    required this.model,
    required this.onEndpoint,
    required this.onModel,
    required this.loadModels,
    required this.onRun,
    required this.onVerify,
  });

  @override
  State<EvalReceiptPanel> createState() => _EvalReceiptPanelState();
}

class _EvalReceiptPanelState extends State<EvalReceiptPanel> {
  bool _running = false;
  bool _verifying = false;
  Map<String, dynamic>? _runDoc; // the sealed run body
  String? _runError; // a provider/credential error reason
  Map<String, dynamic>? _verifyDoc; // the VERIFY path (expects MATCH)
  Map<String, dynamic>? _corruptDoc; // the CORRUPT path (expects TAMPERED)

  Map<String, dynamic>? get _receipt {
    final r = _runDoc?['receipt'];
    return r is Map ? Map<String, dynamic>.from(r) : null;
  }

  Future<void> _run() async {
    if (widget.endpoint == null || _running) return;
    setState(() {
      _running = true;
      _runError = null;
      _verifyDoc = null;
      _corruptDoc = null;
    });
    Map<String, dynamic> r;
    try {
      r = await widget.onRun();
    } catch (e) {
      r = {'error': '$e'};
    }
    if (!mounted) return;
    setState(() {
      _running = false;
      if (r['receipt'] is Map) {
        _runDoc = r;
      } else {
        _runDoc = null;
        _runError = '${r['error'] ?? 'the run returned no receipt'}';
      }
    });
  }

  Future<void> _verify() async {
    final receipt = _receipt;
    if (receipt == null || _verifying) return;
    setState(() => _verifying = true);
    Map<String, dynamic> v;
    try {
      v = await widget.onVerify(receipt);
    } catch (e) {
      v = {'verdict': 'UNVERIFIABLE', 'detail': '$e'};
    }
    if (!mounted) return;
    setState(() {
      _verifying = false;
      _verifyDoc = v;
    });
  }

  Future<void> _corrupt() async {
    final receipt = _receipt;
    if (receipt == null || _verifying) return;
    // Flip one hex char of a COPY, client-side. The stored receipt is never
    // touched: this proves the seal's refusal without corrupting the record.
    final copy = flipOneHexChar(receipt);
    setState(() => _verifying = true);
    Map<String, dynamic> v;
    try {
      v = await widget.onVerify(copy);
    } catch (e) {
      v = {'verdict': 'UNVERIFIABLE', 'detail': '$e'};
    }
    if (!mounted) return;
    setState(() {
      _verifying = false;
      _corruptDoc = v;
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('eval run'),
      const SizedBox(height: FwLayout.s3),
      _controls(t),
      if (_runError != null) ...[
        const SizedBox(height: FwLayout.s3),
        HonestNull('Provider error: $_runError'),
      ],
      if (_runDoc == null && _runError == null && !_running) ...[
        const SizedBox(height: FwLayout.s3),
        const HonestNull(
            'No receipt yet. Pick an endpoint and run an eval; the outcome '
            'seals into a receipt anyone can verify offline.'),
      ],
      if (_running) ...[
        const SizedBox(height: FwLayout.s3),
        Text('running eval…', style: fwMono(t, size: 11.5, color: t.inkFaint)),
      ],
      if (_runDoc != null) ...[
        const SizedBox(height: FwLayout.s4),
        _resultCard(t),
      ],
    ]);
  }

  Widget _controls(FwTokens t) {
    return Wrap(
      spacing: FwLayout.s3,
      runSpacing: FwLayout.s2,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        if (widget.endpoints.isNotEmpty)
          ModelPickerButton(
            endpoints: widget.endpoints,
            current: widget.endpoint,
            enabled: !_running,
            onSelect: widget.onEndpoint,
          )
        else
          Text('no endpoints in the roster',
              style: fwMono(t, size: 11, color: t.inkFaint)),
        if (widget.endpoint != null)
          ModelSelectorButton(
            loadModels: widget.loadModels,
            current: widget.model,
            enabled: !_running,
            onSelect: widget.onModel,
          ),
        FilledButton(
          onPressed: (widget.endpoint == null || _running) ? null : _run,
          child: Text(_running ? 'Running…' : 'Run eval'),
        ),
      ],
    );
  }

  Widget _resultCard(FwTokens t) {
    final results = (_runDoc?['results'] as List?) ?? const [];
    final accepted = results
        .whereType<Map>()
        .where((r) => '${r['accepted']}' == 'true' || r['accepted'] == true)
        .length;
    final sealHex = '${(_receipt?['seal'] as Map?)?['hex'] ?? ''}';
    final modelRef = '${_runDoc?['model_ref'] ?? ''}';
    final receiptFile = '${_runDoc?['receipt_file'] ?? ''}';
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        for (final r in results.whereType<Map>()) _taskRow(t, r),
        const SizedBox(height: FwLayout.s3),
        Divider(height: 1, color: t.hairline),
        const SizedBox(height: FwLayout.s3),
        Text('${results.length} tasks · $accepted accepted',
            style: fwMono(t, size: 12, weight: FontWeight.w600)),
        const SizedBox(height: FwLayout.s2),
        if (modelRef.isNotEmpty) HashText('model', modelRef, keep: 40),
        HashText('seal', sealHex, keep: 32),
        if (receiptFile.isNotEmpty)
          Text(receiptFile, style: fwMono(t, size: 10.5, color: t.inkFaint)),
        const SizedBox(height: FwLayout.s4),
        Wrap(spacing: FwLayout.s3, runSpacing: FwLayout.s2, children: [
          FilledButton.tonal(
            onPressed: _verifying ? null : _verify,
            child: Text(_verifying ? 'Verifying…' : 'Verify'),
          ),
          OutlinedButton(
            onPressed: _verifying ? null : _corrupt,
            child: const Text('Corrupt one byte'),
          ),
        ]),
        if (_verifyDoc != null) ...[
          const SizedBox(height: FwLayout.s3),
          VerifyStateRow(doc: _verifyDoc!),
        ],
        if (_corruptDoc != null) ...[
          const SizedBox(height: FwLayout.s3),
          TamperStateCard(doc: _corruptDoc!),
        ],
      ]),
    );
  }

  Widget _taskRow(FwTokens t, Map r) => Padding(
        padding: const EdgeInsets.only(bottom: FwLayout.s2),
        child: Row(children: [
          VerdictDot(_taskStatus(r), size: 7),
          const SizedBox(width: FwLayout.s2),
          Expanded(
            child: Text('${r['task_id'] ?? ''}',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: fwMono(t, size: 11.5, color: t.inkSoft)),
          ),
          Text('${r['verdict'] ?? ''}',
              style: fwMono(t, size: 10.5, color: t.inkFaint)),
        ]),
      );

  String _taskStatus(Map r) {
    final accepted = '${r['accepted']}' == 'true' || r['accepted'] == true;
    final verdict = '${r['verdict'] ?? ''}'.toUpperCase();
    if (accepted || verdict == 'PASS' || verdict == 'MATCH') return 'verified';
    if (verdict.contains('UNVERIF')) return 'unverifiable';
    return 'drift';
  }

}
