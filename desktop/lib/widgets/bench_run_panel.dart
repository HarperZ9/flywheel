// bench_run_panel.dart -- run the private verified benchmark.
//
// Every attempt is disposed by a real subprocess gate, so this reaches both
// the network and the shell: it goes through the grant sheet, and the grant
// binds the task set, the endpoints, and the timeout the operator approved.
// The result carries its own denominator and its own does-not-prove line;
// neither is summarized away here.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import 'bench_task_editor.dart';
import 'fw.dart';
import 'operation_grant_sheet.dart';

class BenchRunPanel extends StatefulWidget {
  final GatewayClient client;
  final List<EndpointRow> endpoints;
  const BenchRunPanel(
      {super.key, required this.client, required this.endpoints});

  @override
  State<BenchRunPanel> createState() => _BenchRunPanelState();
}

class _BenchRunPanelState extends State<BenchRunPanel> {
  final List<BenchTask> _tasks = [BenchTask()];
  final _selected = <String>{};
  final _timeout = TextEditingController(text: '120');
  Map<String, dynamic>? _result;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    for (final task in _tasks) {
      task.dispose();
    }
    _timeout.dispose();
    super.dispose();
  }

  bool get _ready =>
      !_busy &&
      _selected.isNotEmpty &&
      _tasks.isNotEmpty &&
      _tasks.every((task) => task.complete);

  Future<void> _run() async {
    if (!_ready) return;
    final seconds = double.tryParse(_timeout.text.trim()) ?? 120;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final requestId = 'bench-${DateTime.now().microsecondsSinceEpoch}';
      final r = await authorizeGatewayOperation<Map<String, dynamic>>(
        context,
        GatewayOperation.exact(
          action: 'bench.run',
          clientRequestId: requestId,
          operation: {
            'tasks': [for (final task in _tasks) task.toJson()],
            'endpoints': _selected.toList()..sort(),
            'timeout_s': seconds,
          },
        ),
        (body) => widget.client.postJson('/api/bench/run', body,
            timeout: const Duration(minutes: 30)),
        currentOperation: () => null,
      );
      if (mounted) setState(() => _result = r);
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
          const Kicker('private benchmark'),
          const SizedBox(height: FwLayout.s1),
          Text(
              'Each attempt is judged by running its gate command, not by a '
              'model grading a model. The run reports how many attempts went '
              'into every rate, so a number can be checked against what '
              'produced it.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s4),
          BenchTaskEditor(
            tasks: _tasks,
            enabled: !_busy,
            onAdd: () => setState(() => _tasks.add(BenchTask())),
            onRemove: (i) => setState(() => _tasks.removeAt(i).dispose()),
            onChanged: () => setState(() {}),
          ),
          const SizedBox(height: FwLayout.s4),
          _endpointPicker(t),
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            SizedBox(
              width: 150,
              child: TextField(
                controller: _timeout,
                enabled: !_busy,
                keyboardType: TextInputType.number,
                style: fwMono(t, size: 11.5, color: t.ink),
                decoration: const InputDecoration(
                    isDense: true, labelText: 'timeout seconds'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            FilledButton(
              onPressed: _ready ? _run : null,
              child: Text(_busy ? 'Running…' : 'Run benchmark'),
            ),
          ]),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('The benchmark did not complete: $_error'),
          ],
          if (_result != null) ...[
            const SizedBox(height: FwLayout.s4),
            _resultBlock(t, _result!),
          ],
        ],
      ),
    );
  }

  Widget _endpointPicker(FwTokens t) {
    if (widget.endpoints.isEmpty) {
      return const HonestNull(
          'No endpoint is configured, so there is nothing to benchmark.');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker('endpoints'),
        const SizedBox(height: FwLayout.s2),
        Wrap(
          spacing: FwLayout.s2,
          runSpacing: FwLayout.s2,
          children: [
            for (final row in widget.endpoints)
              FilterChip(
                label: Text(row.name, style: fwMono(t, size: 11)),
                selected: _selected.contains(row.name),
                onSelected: _busy
                    ? null
                    : (on) => setState(() => on
                        ? _selected.add(row.name)
                        : _selected.remove(row.name)),
              ),
          ],
        ),
      ],
    );
  }

  Widget _resultBlock(FwTokens t, Map<String, dynamic> r) {
    final bench = r['bench'];
    final frontier = r['frontier'];
    if (bench is! Map || frontier is! Map) {
      return const HonestNull('The run returned no benchmark to read.');
    }
    final denominator = bench['denominator'];
    final rankings =
        frontier['rankings'] is List ? frontier['rankings'] as List : const [];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(children: [
          const Kicker('verified pass rate'),
          if (r['event_blocked'] == true) ...[
            const SizedBox(width: FwLayout.s2),
            const VerdictPill('hook blocked', status: 'drift'),
          ],
        ]),
        const SizedBox(height: FwLayout.s2),
        if (denominator is Map)
          Text(
              '${denominator['attempts'] ?? '—'} attempts · '
              '${denominator['tasks'] ?? '—'} tasks · '
              '${denominator['endpoints'] ?? '—'} endpoints · '
              '${denominator['replicates'] ?? '—'} replicates',
              style: fwMono(t, size: 11, color: t.inkFaint)),
        const SizedBox(height: FwLayout.s2),
        for (final row in rankings.whereType<Map>()) _rankRow(t, row),
        const SizedBox(height: FwLayout.s3),
        HashText('bench', '${bench['bench_sha256'] ?? ''}', keep: 16),
        if (bench['does_not_prove'] != null) ...[
          const SizedBox(height: FwLayout.s2),
          HonestNull('${bench['does_not_prove']}'),
        ],
      ],
    );
  }

  Widget _rankRow(FwTokens t, Map row) {
    // The interval is the honest width of the estimate. Printing the rate
    // alone would read as precision the attempt count does not support.
    final interval = row['wilson_95'];
    final band = interval is List && interval.length == 2
        ? '[${interval[0]}, ${interval[1]}]'
        : 'no interval at this count';
    return Padding(
      padding: const EdgeInsets.only(bottom: 3),
      child: Row(children: [
        Expanded(
            flex: 3,
            child: Text('${row['endpoint'] ?? ''}',
                overflow: TextOverflow.ellipsis,
                style: fwMono(t, size: 11.5, color: t.ink))),
        Expanded(
            flex: 2,
            child: Text(
                '${row['verified_passes'] ?? '—'}/${row['attempts'] ?? '—'}',
                style: fwMono(t, size: 11, color: t.inkSoft))),
        Expanded(
            flex: 3,
            child: Text(band,
                overflow: TextOverflow.ellipsis,
                style: fwMono(t, size: 11, color: t.inkFaint))),
      ]),
    );
  }
}
