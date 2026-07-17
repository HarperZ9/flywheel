// graph_editor.dart — the node canvas: build a creative graph by hand.
// Add nodes of any op, wire each one's inputs from the nodes that cannot
// cycle back to it, run it live through the same witnessed route the presets
// use, and export the spec. The model (graph_edit.dart) owns every rule; this
// widget only shows it and runs it, so a graph that says it is runnable is.

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/graph_edit.dart';
import '../theme/flywheel_theme.dart';
import 'composer_controls.dart';
import 'fw.dart';

class GraphEditor extends StatefulWidget {
  final GatewayClient client;
  const GraphEditor({super.key, required this.client});

  @override
  State<GraphEditor> createState() => _GraphEditorState();
}

class _GraphEditorState extends State<GraphEditor> {
  final _g = GraphEdit();
  bool _busy = false;
  Map<String, dynamic>? _receipt;
  final Map<String, Uint8List> _outputs = {};
  String? _error, _savedTo;

  Future<void> _run() async {
    final why = _g.whyNotRunnable();
    if (why != null) {
      setState(() => _error = why);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _savedTo = null;
    });
    try {
      final r = await widget.client
          .studioGraph(_g.toNodes(480, 320), _g.toEdges());
      if (!mounted) return;
      setState(() {
        if (r['refused'] == true || r['error'] != null) {
          _error = (r['refusals'] is List && (r['refusals'] as List).isNotEmpty)
              ? '${(r['refusals'] as List).first}'
              : '${r['error'] ?? 'refused'}';
          _outputs.clear();
          _receipt = null;
        } else {
          _outputs
            ..clear()
            ..addAll({
              for (final e in (r['outputs'] as Map<String, dynamic>).entries)
                e.key: base64Decode('${e.value}')
            });
          _receipt = r['receipt'] as Map<String, dynamic>?;
        }
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _export() async {
    final rc = _receipt;
    if (rc == null) return;
    try {
      final home = Platform.environment['USERPROFILE'] ??
          Platform.environment['HOME'] ??
          '.';
      final doc = const JsonEncoder.withIndent('  ').convert({
        'schema': 'flywheel.fwgraph/v1',
        'preset': 'hand-authored',
        'nodes': _g.toNodes(480, 320),
        'edges': _g.toEdges(),
        'graph_id': rc['graph_id'],
      });
      final f = File('$home${Platform.pathSeparator}Downloads'
          '${Platform.pathSeparator}graph-${rc['graph_id']}.fwgraph');
      f.writeAsStringSync(doc);
      setState(() => _savedTo = f.path);
    } catch (e) {
      setState(() => _error = 'export failed: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final why = _g.whyNotRunnable();
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        _addRow(t),
        const SizedBox(height: FwLayout.s2),
        if (_g.nodes.isEmpty)
          Text('An empty canvas. Add a source to begin.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted))
        else
          for (final n in _g.nodes) _nodeRow(t, n),
        const SizedBox(height: FwLayout.s3),
        Row(children: [
          FilledButton(
            onPressed: (_busy || why != null) ? null : _run,
            child: Text(_busy ? 'Running…' : 'Run graph'),
          ),
          const SizedBox(width: FwLayout.s3),
          if (why != null)
            Flexible(
              child: Text(why,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: fwMono(t, size: 10.5, color: t.inkFaint)),
            )
          else if (_receipt != null)
            OutlinedButton(
                onPressed: _export, child: const Text('.fwgraph')),
        ]),
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s2),
          HonestNull(_error!),
        ],
        if (_receipt != null) _result(t),
      ]),
    );
  }

  Widget _addRow(FwTokens t) => Wrap(
        spacing: FwLayout.s2,
        runSpacing: FwLayout.s1,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Text('add', style: fwMono(t, size: 10.5, color: t.inkFaint)),
          for (final op in [...graphSources, ...graphTransforms, ...graphMerges])
            OutlinedButton(
              onPressed: () => setState(() => _g.add(op)),
              style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  minimumSize: const Size(0, 30)),
              child: Text(op, style: fwMono(t, size: 10.5)),
            ),
        ],
      );

  Widget _nodeRow(FwTokens t, GraphNodeEdit n) {
    final want = arityOf(n.op);
    final candidates = _g.candidateInputs(n);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(children: [
        SizedBox(
            width: 64,
            child: Text(n.id, style: fwMono(t, size: 11, color: t.inkMuted))),
        SizedBox(
            width: 90,
            child: Text(n.op, style: fwMono(t, size: 11.5))),
        if (graphSources.contains(n.op)) ...[
          Text('seed', style: fwMono(t, size: 10, color: t.inkFaint)),
          const SizedBox(width: 4),
          SizedBox(
            width: 56,
            child: TextFormField(
              initialValue: '${n.seed}',
              style: fwMono(t, size: 11),
              onChanged: (v) => n.seed = int.tryParse(v.trim()) ?? n.seed,
            ),
          ),
        ],
        for (var i = 0; i < want; i++) ...[
          const SizedBox(width: FwLayout.s2),
          LabeledPicker(
            label: 'in${i + 1}',
            value: i < n.inputs.length ? n.inputs[i] : null,
            options: candidates,
            onChanged: (v) => setState(() {
              while (n.inputs.length <= i) {
                n.inputs.add(candidates.isNotEmpty ? candidates.first : '');
              }
              if (v != null) n.inputs[i] = v;
            }),
          ),
        ],
        const Spacer(),
        IconButton(
          icon: const Icon(Icons.close, size: 14),
          onPressed: () => setState(() => _g.remove(n.id)),
        ),
      ]),
    );
  }

  Widget _result(FwTokens t) {
    final rc = _receipt!;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const SizedBox(height: FwLayout.s3),
      Wrap(
        spacing: FwLayout.s2,
        runSpacing: FwLayout.s2,
        children: [
          for (final e in _outputs.entries)
            ClipRRect(
              borderRadius: BorderRadius.circular(3),
              child: Image.memory(e.value, width: 132, fit: BoxFit.cover),
            ),
        ],
      ),
      const SizedBox(height: FwLayout.s2),
      Row(children: [
        VerdictPill('graph ${rc['graph_id'] ?? ''}', status: 'verified'),
        if ((rc['cache_hits'] ?? 0) != 0) ...[
          const SizedBox(width: FwLayout.s2),
          VerdictPill('${rc['cache_hits']} cached', status: 'verified'),
        ],
      ]),
      if (_savedTo != null) ...[
        const SizedBox(height: FwLayout.s2),
        Text('saved $_savedTo',
            style: fwMono(t, size: 10.5, color: t.inkMuted),
            overflow: TextOverflow.ellipsis),
      ],
    ]);
  }
}
