// suite_audit_panel.dart -- can this acceptance suite refuse wrong code?
//
// The suite is mutated a bounded number of times and re-run. A mutant that
// survives names a wrong-code change the suite accepted, which is the only
// evidence that "one suite, no negotiation" means anything. A timeout decides
// nothing, so indeterminate runs leave the denominator rather than pad it,
// and the panel says how many were excluded. Running the suite is subprocess
// execution against a real project, so the operator grants it first.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'operation_grant_sheet.dart';

class SuiteAuditPanel extends StatefulWidget {
  final GatewayClient client;
  const SuiteAuditPanel({super.key, required this.client});

  @override
  State<SuiteAuditPanel> createState() => _SuiteAuditPanelState();
}

class _SuiteAuditPanelState extends State<SuiteAuditPanel> {
  final _path = TextEditingController();
  final _oracle = TextEditingController(text: 'python -m pytest tests/ -q');
  final _mutants = TextEditingController(text: '5');
  Map<String, dynamic>? _report;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _path.dispose();
    _oracle.dispose();
    _mutants.dispose();
    super.dispose();
  }

  Future<void> _audit() async {
    final path = _path.text.trim();
    if (path.isEmpty || _busy) return;
    final mutants = int.tryParse(_mutants.text.trim()) ?? 5;
    if (mutants < 1 || mutants > 20) {
      setState(() => _error = 'max mutants must be an integer in 1..20');
      return;
    }
    final oracle = _oracle.text.trim();
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final requestId = 'suite-${DateTime.now().microsecondsSinceEpoch}';
      final r = await authorizeGatewayOperation<Map<String, dynamic>>(
        context,
        GatewayOperation.exact(
          action: 'suite.audit',
          clientRequestId: requestId,
          operation: {
            'path': path,
            'max_mutants': mutants,
            if (oracle.isNotEmpty) 'oracle_cmd': oracle,
          },
        ),
        (body) => widget.client.postJson('/api/suite', body,
            timeout: const Duration(minutes: 30)),
        currentOperation: () => null,
      );
      if (mounted) setState(() => _report = r);
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
          const Kicker('suite audit · the refusal floor, measured'),
          const SizedBox(height: FwLayout.s3),
          TextField(
            controller: _path,
            enabled: !_busy,
            style: fwMono(t, size: 11.5, color: t.ink),
            decoration: const InputDecoration(
                isDense: true,
                labelText: 'project path',
                hintText: 'a directory whose suite passes today'),
          ),
          const SizedBox(height: FwLayout.s2),
          Row(children: [
            Expanded(
              child: TextField(
                controller: _oracle,
                enabled: !_busy,
                style: fwMono(t, size: 11.5, color: t.ink),
                decoration: const InputDecoration(
                    isDense: true, labelText: 'oracle command'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            SizedBox(
              width: 110,
              child: TextField(
                controller: _mutants,
                enabled: !_busy,
                keyboardType: TextInputType.number,
                style: fwMono(t, size: 11.5, color: t.ink),
                decoration: const InputDecoration(
                    isDense: true, labelText: 'max mutants'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            FilledButton(
              onPressed: _busy ? null : _audit,
              child: Text(_busy ? 'Mutating…' : 'Audit the suite'),
            ),
          ]),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('The audit did not run: $_error'),
          ],
          if (_report != null) ...[
            const SizedBox(height: FwLayout.s3),
            _reportBlock(t, _report!),
          ],
        ],
      ),
    );
  }

  Widget _reportBlock(FwTokens t, Map<String, dynamic> r) {
    if (r['error'] != null) {
      return HonestNull('${r['error']}');
    }
    final survivors =
        r['survivors'] is List ? (r['survivors'] as List) : const [];
    final indeterminate =
        r['indeterminate'] is List ? (r['indeterminate'] as List) : const [];
    final rate = r['kill_rate'];
    final restored = r['restored'] == true;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (r['reference_ok'] == false)
          const HonestNull(
              'Broken reference: the suite fails on the project\'s own '
              'source, so there is nothing to audit until it passes.')
        else ...[
          Row(children: [
            VerdictPill(
                rate is num ? 'kill rate ${rate.toStringAsFixed(2)}' : 'no rate',
                status: rate is num
                    ? (rate >= 1.0 ? 'verified' : 'drift')
                    : 'unverifiable'),
            const SizedBox(width: FwLayout.s3),
            Text(
                'killed ${r['killed'] ?? '—'} of ${r['attempted'] ?? '—'} '
                'attempted, ${indeterminate.length} undecided, '
                '${r['wall_seconds'] ?? '—'}s',
                style: fwMono(t, size: 11, color: t.inkFaint)),
          ]),
          if (rate == null) ...[
            const SizedBox(height: FwLayout.s2),
            const HonestNull(
                'Every mutant was indeterminate, so no rate exists. An '
                'undecided run is excluded rather than counted as a kill.'),
          ],
          const SizedBox(height: FwLayout.s2),
          if (survivors.isEmpty)
            Text('No survivor: every decided mutant was refused.',
                style: fwMono(t, size: 11, color: t.inkSoft))
          else
            for (final s in survivors)
              Padding(
                padding: const EdgeInsets.only(bottom: 3),
                child: SelectableText('survivor · ${_survivor(s)}',
                    style: fwMono(t, size: 11, color: t.ink)),
              ),
        ],
        if (!restored) ...[
          const SizedBox(height: FwLayout.s2),
          const HonestNull(
              'A mutated file was NOT restored to its original bytes. Check '
              'the project before trusting anything else it reports.'),
        ],
        if (r['note'] != null) ...[
          const SizedBox(height: FwLayout.s2),
          Text('${r['note']}',
              style: fwMono(t, size: 10.5, color: t.inkFaint)),
        ],
      ],
    );
  }

  /// A survivor is a record, but the engine may name it as a bare path.
  /// Rendering the map's toString would put Dart syntax on screen.
  String _survivor(Object? s) {
    if (s is Map) {
      final path = s['path'] ?? s['file'] ?? '';
      final line = s['line'] ?? s['orig_line'];
      return line == null ? '$path' : '$path:$line';
    }
    return '$s';
  }
}
