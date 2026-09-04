// frontier_panel.dart -- which model this machine should run, decided by
// measurements taken here.
//
// The probe is one real generation against a live endpoint, so it reaches the
// network and costs whatever that endpoint costs: it goes through the grant
// sheet like any other outward operation. The table below it composes those
// probes with the paired-arm bench. Unknowns stay null and render as a dash;
// filling one with an estimate would turn a measurement into a guess.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'operation_grant_sheet.dart';

class FrontierPanel extends StatefulWidget {
  final GatewayClient client;
  final List<EndpointRow> endpoints;
  const FrontierPanel(
      {super.key, required this.client, required this.endpoints});

  @override
  State<FrontierPanel> createState() => _FrontierPanelState();
}

class _FrontierPanelState extends State<FrontierPanel> {
  final _disk = TextEditingController();
  Map<String, dynamic>? _table;
  Map<String, dynamic>? _probe;
  String? _endpoint;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _loadTable();
  }

  @override
  void dispose() {
    _disk.dispose();
    super.dispose();
  }

  Future<void> _loadTable() async {
    try {
      final r = await widget.client.getJson('/api/frontier');
      if (mounted) setState(() => _table = r);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _runProbe() async {
    final endpoint = _endpoint;
    if (endpoint == null || endpoint.isEmpty || _busy) return;
    // A blank disk size means unknown, and unknown is a legitimate answer:
    // the table then leaves capability-per-GB null rather than inventing one.
    final disk = double.tryParse(_disk.text.trim());
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final requestId = 'capability-${DateTime.now().microsecondsSinceEpoch}';
      final r = await authorizeGatewayOperation<Map<String, dynamic>>(
        context,
        GatewayOperation.exact(
          action: 'capability.probe',
          clientRequestId: requestId,
          operation: {
            'endpoint': endpoint,
            if (disk != null && disk > 0) 'disk_gb': disk,
          },
        ),
        (body) => widget.client.postJson('/api/capability', body,
            timeout: const Duration(seconds: 120)),
        currentOperation: () => null,
      );
      if (!mounted) return;
      setState(() => _probe = r);
      await _loadTable();
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
          const Kicker('frontier'),
          const SizedBox(height: FwLayout.s1),
          Text(
              'A probe is one measured generation against a live endpoint. '
              'The table pairs those probes with the bench\'s verified rates, '
              'so "which model fits this machine" is answered by numbers '
              'produced here rather than by an imported leaderboard.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          _controls(t),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s2),
            HonestNull('The probe failed: $_error'),
          ],
          if (_probe != null) ...[
            const SizedBox(height: FwLayout.s3),
            _probeResult(t, _probe!),
          ],
          const SizedBox(height: FwLayout.s4),
          _tableBlock(t),
        ],
      ),
    );
  }

  Widget _controls(FwTokens t) => Wrap(
        spacing: FwLayout.s3,
        runSpacing: FwLayout.s2,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          SizedBox(
            width: 220,
            child: DropdownButtonFormField<String>(
              initialValue: _endpoint,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'endpoint'),
              style: fwMono(t, size: 11.5, color: t.ink),
              items: [
                for (final row in widget.endpoints)
                  DropdownMenuItem(value: row.name, child: Text(row.name)),
              ],
              onChanged: _busy ? null : (v) => setState(() => _endpoint = v),
            ),
          ),
          SizedBox(
            width: 150,
            child: TextField(
              controller: _disk,
              keyboardType: TextInputType.number,
              style: fwMono(t, size: 11.5, color: t.ink),
              decoration: const InputDecoration(
                  labelText: 'disk GB', hintText: 'leave blank if unknown'),
            ),
          ),
          FilledButton(
            onPressed: _busy || _endpoint == null ? null : _runProbe,
            child: Text(_busy ? 'Probing…' : 'Probe this machine'),
          ),
        ],
      );

  Widget _probeResult(FwTokens t, Map<String, dynamic> p) {
    final error = p['error'];
    if (error != null) {
      return HonestNull('The endpoint did not answer: $error');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
            '${p['endpoint']}  ·  ${p['tok_s'] ?? '—'} tok/s  ·  '
            '${p['latency_s'] ?? '—'} s  ·  ${p['tokens_approx'] ?? '—'} tokens',
            style: fwMono(t, size: 11.5, color: t.ink)),
        const SizedBox(height: 4),
        HashText('output', '${p['output_sha256'] ?? ''}', keep: 16),
        if (p['note'] != null) ...[
          const SizedBox(height: 4),
          Text('${p['note']}', style: fwMono(t, size: 10.5, color: t.inkFaint)),
        ],
      ],
    );
  }

  Widget _tableBlock(FwTokens t) {
    final table = _table;
    if (table == null) {
      return const HonestNull('The frontier table has not been read yet.');
    }
    final rows = table['rows'] is List ? (table['rows'] as List) : const [];
    if (rows.isEmpty) {
      return const HonestNull(
          'No endpoint has been probed on this machine, so the frontier is '
          'empty. Probe one above; nothing is carried in from elsewhere.');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker('measured here'),
        const SizedBox(height: FwLayout.s2),
        _headerRow(t),
        for (final row in rows.whereType<Map>()) _dataRow(t, row),
        if (table['note'] != null) ...[
          const SizedBox(height: FwLayout.s2),
          Text('${table['note']}',
              style: fwMono(t, size: 10.5, color: t.inkFaint)),
        ],
      ],
    );
  }


  Widget _headerRow(FwTokens t) => Padding(
        padding: const EdgeInsets.only(bottom: 4),
        child: Row(children: [
          Expanded(flex: 3, child: _cell(t, 'endpoint', faint: true)),
          Expanded(child: _cell(t, 'tok/s', faint: true)),
          Expanded(child: _cell(t, 'GB', faint: true)),
          Expanded(child: _cell(t, 'bare', faint: true)),
          Expanded(child: _cell(t, 'verified', faint: true)),
          Expanded(flex: 2, child: _cell(t, 'per GB', faint: true)),
        ]),
      );

  Widget _dataRow(FwTokens t, Map row) => Padding(
        padding: const EdgeInsets.only(bottom: 3),
        child: Row(children: [
          Expanded(flex: 3, child: _cell(t, '${row['endpoint'] ?? ''}')),
          Expanded(child: _cell(t, _num(row['tok_s']))),
          Expanded(child: _cell(t, _num(row['disk_gb']))),
          Expanded(child: _cell(t, _num(row['bare_rate']))),
          Expanded(child: _cell(t, _num(row['verified_rate']))),
          Expanded(
            flex: 2,
            child: Row(children: [
              _cell(t, _num(row['capability_per_gb'])),
              if (row['uplift_separated'] == true) ...[
                const SizedBox(width: FwLayout.s2),
                const VerdictPill('separated', status: 'verified'),
              ],
            ]),
          ),
        ]),
      );

  Widget _cell(FwTokens t, String text, {bool faint = false}) => Text(text,
      overflow: TextOverflow.ellipsis,
      style: fwMono(t, size: 11, color: faint ? t.inkFaint : t.inkSoft));

  /// A null is an unmeasured quantity, not a zero.
  String _num(Object? value) => value is num ? '$value' : '—';
}
