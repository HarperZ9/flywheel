import 'package:flutter/material.dart';
import '../client/agent_trace_reader.dart';
import '../controllers/agent_trace_controller.dart';
import '../models/agent_trace.dart';
import '../theme/flywheel_theme.dart';
import 'agent_trace_record_view.dart';
import 'fw.dart';

/// Opt-in private originals, confined to this widget's lifetime.
class AgentTraceViewer extends StatefulWidget {
  final TraceProjection projection;
  final AgentTraceReader reader;
  const AgentTraceViewer(
      {super.key, required this.projection, required this.reader});
  @override
  State<AgentTraceViewer> createState() => _AgentTraceViewerState();
}

class _AgentTraceViewerState extends State<AgentTraceViewer> {
  late AgentTraceController _state;
  int _selected = 0;
  @override
  void initState() {
    super.initState();
    _create();
  }

  void _create() {
    _state = AgentTraceController(widget.reader, widget.projection)
      ..addListener(_changed);
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  @override
  void didUpdateWidget(covariant AgentTraceViewer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.projection.projectionSha256 !=
            widget.projection.projectionSha256 ||
        oldWidget.reader != widget.reader) {
      _state.dispose();
      _selected = 0;
      _create();
    }
  }

  @override
  void dispose() {
    _state.dispose();
    super.dispose();
  }

  Future<void> _read() async {
    final state = _state;
    await state.loadNext();
    if (mounted && state == _state && state.records.isNotEmpty) {
      setState(() => _selected = state.records.length - 1);
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.projection, records = _state.records, t = context.fw;
    return HairlineCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('Private execution trace'),
      const SizedBox(height: FwLayout.s2),
      Text('${p.state} · ${p.recordCount} retained records',
          style: Theme.of(context).textTheme.bodyMedium),
      if (p.isPartialExecution)
        Text('Partial execution: only the accepted prefix is retained.',
            style: Theme.of(context).textTheme.bodyMedium),
      Text(
          'Omitted from public metadata: private content. Credentials are excluded; '
          'upstream output limits still apply.',
          style: Theme.of(context)
              .textTheme
              .bodyMedium
              ?.copyWith(color: t.inkMuted)),
      Text(
          'Hashes establish recorded bytes and bindings, not semantic truth, '
          'source truth, or unlimited tool output.',
          style: Theme.of(context)
              .textTheme
              .bodyMedium
              ?.copyWith(color: t.inkMuted)),
      const SizedBox(height: FwLayout.s2),
      SelectableText(
          'Operation ${p.operationRef}\nJourney ${p.journeyRef}\nTrace ${p.traceRef}',
          style: fwMono(t, size: 11)),
      if (p.recordCount == 0)
        const Text('Unavailable: no private records were accepted.'),
      if (records.isNotEmpty) ...[
        const SizedBox(height: FwLayout.s2),
        Text(
            _state.complete
                ? 'Hashes match the advertised ${p.isRunning ? 'prefix' : 'trace'} head.'
                : 'Partial read: ${records.length} of ${p.recordCount} records. Final head not checked.',
            style: Theme.of(context).textTheme.bodyMedium),
        Wrap(
            spacing: FwLayout.s2,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text('Record ${_selected + 1} of ${records.length} loaded'),
              TextButton(
                  onPressed:
                      _selected > 0 ? () => setState(() => _selected--) : null,
                  child: const Text('Previous record')),
              TextButton(
                  onPressed: _selected + 1 < records.length
                      ? () => setState(() => _selected++)
                      : null,
                  child: const Text('Next loaded record')),
            ]),
        AgentTraceRecordView(
            key: ValueKey(records[_selected].recordSha256),
            record: records[_selected]),
      ],
      if (_state.failure != null)
        Padding(
            padding: const EdgeInsets.only(top: FwLayout.s2),
            child: Text(_failure(_state.failure!),
                style: Theme.of(context).textTheme.bodyMedium)),
      if (_state.loading)
        const Padding(
            padding: EdgeInsets.all(FwLayout.s2),
            child: Text('Reading private record…')),
      if (!_state.complete)
        TextButton.icon(
            onPressed: _state.loading ? null : _read,
            icon: const Icon(Icons.receipt_long_outlined, size: 16),
            label: Text(_state.failure != null
                ? 'Retry read'
                : records.isEmpty
                    ? 'Read private trace'
                    : 'Load next record')),
    ]));
  }
}

String _failure(TraceReadFailure failure) => switch (failure) {
      TraceReadFailure.unavailable =>
        'Unavailable: the gateway has no accessible private record.',
      TraceReadFailure.unauthorized =>
        'Unavailable: gateway authentication is required.',
      TraceReadFailure.integrity =>
        'Unavailable: record integrity or operation binding did not match.',
      TraceReadFailure.limit =>
        'Unavailable: the private read exceeded its size or complexity limit.',
      TraceReadFailure.transport =>
        'Unavailable: the gateway read did not complete. Retry reads the same record.',
      TraceReadFailure.cancelled => 'Private read cancelled.',
    };
