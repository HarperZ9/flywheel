// graph_panel.dart — the creative graph: branches that testify. Preset
// DAGs run through /api/studio/graph; the trail renders every node with
// its inputs and chain, and the graph id witnesses the whole tree.

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class _Preset {
  final String name;
  final String blurb;
  final List<Map<String, dynamic>> Function(int seed) nodes;
  final List<Map<String, dynamic>> edges;
  const _Preset(this.name, this.blurb, this.nodes, this.edges);
}

final List<_Preset> _presets = [
  _Preset(
    'wire × harmonograph',
    'two sources blend, the lane dithers, the film closes',
    (s) => [
      {'id': 'wire', 'op': 'wireframe',
       'args': {'primitive': 'orbit-sphere', 'seed': s,
                'width': 640, 'height': 400}},
      {'id': 'harmo', 'op': 'harmonograph',
       'args': {'width': 640, 'height': 400, 'samples': 900}},
      {'id': 'mix', 'op': 'blend', 'args': {'alpha': 0.45}},
      {'id': 'dith', 'op': 'dither', 'args': {'levels': 3, 'matrixSize': 8}},
      {'id': 'film', 'op': 'film_frame',
       'args': {'seed': s, 'grain': 0.4, 'vignette': 0.5}},
    ],
    const [
      {'from': 'wire', 'to': 'mix'},
      {'from': 'harmo', 'to': 'mix'},
      {'from': 'mix', 'to': 'dith'},
      {'from': 'dith', 'to': 'film'},
    ],
  ),
  _Preset(
    'plate ∆ plate',
    'two seeds of the same form, differenced: only what changed survives',
    (s) => [
      {'id': 'a', 'op': 'plate',
       'args': {'seed': s, 'width': 640, 'height': 400}},
      {'id': 'b', 'op': 'plate',
       'args': {'seed': s + 1, 'width': 640, 'height': 400}},
      {'id': 'd', 'op': 'difference', 'args': {}},
    ],
    const [
      {'from': 'a', 'to': 'd'},
      {'from': 'b', 'to': 'd'},
    ],
  ),
  _Preset(
    'one source, two fates',
    'a fan-out: the same wireframe sorted and filmed, side by side',
    (s) => [
      {'id': 'src', 'op': 'wireframe',
       'args': {'primitive': 'pyramid', 'seed': s,
                'width': 480, 'height': 320}},
      {'id': 'sort', 'op': 'pixel_sort', 'args': {'threshold': 96}},
      {'id': 'film', 'op': 'film_frame',
       'args': {'seed': s, 'grain': 0.6, 'vignette': 0.6}},
      {'id': 'both', 'op': 'beside', 'args': {}},
    ],
    const [
      {'from': 'src', 'to': 'sort'},
      {'from': 'src', 'to': 'film'},
      {'from': 'sort', 'to': 'both'},
      {'from': 'film', 'to': 'both'},
    ],
  ),
];

class GraphPanel extends StatefulWidget {
  final GatewayClient client;
  const GraphPanel({super.key, required this.client});

  @override
  State<GraphPanel> createState() => _GraphPanelState();
}

class _GraphPanelState extends State<GraphPanel> {
  final _seed = TextEditingController(text: '58');
  int _preset = 0;
  Map<String, dynamic>? _receipt;
  final Map<String, Uint8List> _outputs = {};
  bool _busy = false;
  String? _error, _savedTo;

  @override
  void dispose() {
    _seed.dispose();
    super.dispose();
  }

  Future<void> _run() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _savedTo = null;
    });
    try {
      final p = _presets[_preset];
      final seed = int.tryParse(_seed.text.trim()) ?? 58;
      final r = await widget.client.studioGraph(p.nodes(seed), p.edges);
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

  String get _downloads =>
      '${Platform.environment['USERPROFILE'] ?? Platform.environment['HOME'] ?? '.'}'
      '${Platform.pathSeparator}Downloads';
  Future<void> _save() async {
    final rc = _receipt;
    if (rc == null || _outputs.isEmpty) return;
    try {
      String last = '';
      for (final e in _outputs.entries) {
        final f = File('$_downloads${Platform.pathSeparator}'
            'graph-${rc['graph_id']}-${e.key}.png');
        f.writeAsBytesSync(e.value);
        last = f.path;
      }
      setState(() => _savedTo = last);
    } catch (e) {
      setState(() => _error = 'save failed: $e');
    }
  }

  /// Export the graph as a portable .fwgraph: the spec plus the graph_id it
  /// produced. Reopening re-runs it (cache serves an unchanged spec instantly;
  /// a moved graph_id proves the engine changed under the same spec).
  Future<void> _exportSpec() async {
    final rc = _receipt;
    if (rc == null) return;
    try {
      final p = _presets[_preset];
      final seed = int.tryParse(_seed.text.trim()) ?? 58;
      final doc = const JsonEncoder.withIndent('  ').convert({
        'schema': 'flywheel.fwgraph/v1',
        'preset': p.name,
        'seed': seed,
        'nodes': p.nodes(seed),
        'edges': p.edges,
        'graph_id': rc['graph_id'],
      });
      final f = File('$_downloads${Platform.pathSeparator}'
          '${p.name.replaceAll(RegExp(r'[^a-zA-Z0-9]+'), '-')}'
          '-${rc['graph_id']}.fwgraph');
      f.writeAsStringSync(doc);
      setState(() => _savedTo = f.path);
    } catch (e) {
      setState(() => _error = 'export failed: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
              'Branches, not just lines: sources fan out, merges join, and '
              'every node\'s chain folds its inputs\' chains, so any id '
              'witnesses its whole upstream tree. Reseed one branch and '
              'only its descendants move.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            DropdownButton<int>(
              value: _preset,
              isDense: true,
              style: fwMono(t, size: 11.5).copyWith(color: t.ink),
              items: [
                for (var i = 0; i < _presets.length; i++)
                  DropdownMenuItem(value: i, child: Text(_presets[i].name)),
              ],
              onChanged: (v) => setState(() => _preset = v ?? 0),
            ),
            const SizedBox(width: FwLayout.s3),
            Expanded(
              child: Text(_presets[_preset].blurb,
                  style: fwMono(t, size: 11).copyWith(color: t.inkFaint),
                  overflow: TextOverflow.ellipsis),
            ),
            SizedBox(
              width: 80,
              child: TextField(
                controller: _seed,
                style: fwMono(t, size: 12),
                decoration: const InputDecoration(hintText: 'seed'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            FilledButton(
              onPressed: _busy ? null : _run,
              child: Text(_busy ? 'Running…' : 'Run the graph'),
            ),
          ]),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s2),
            HonestNull(_error!),
          ],
          if (_outputs.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s3),
            SizedBox(
              height: 300,
              child: Row(children: [
                for (final e in _outputs.entries) ...[
                  Expanded(
                    child: Image.memory(e.value,
                        fit: BoxFit.contain,
                        filterQuality: FilterQuality.none),
                  ),
                  const SizedBox(width: FwLayout.s2),
                ],
              ]),
            ),
            const SizedBox(height: FwLayout.s2),
            for (final n in ((_receipt?['nodes'] as List?) ?? const []))
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: Row(children: [
                  const VerdictDot('verified'),
                  const SizedBox(width: FwLayout.s2),
                  Expanded(
                    child: Text(
                        '${(n as Map)['id']}'
                        '${(n['inputs'] as List?)?.isNotEmpty == true ? ' <- ${(n['inputs'] as List).join(' + ')}' : ''}'
                        '  ·  chain ${n['chain']}',
                        style: fwMono(t, size: 11)
                            .copyWith(color: t.inkMuted),
                        overflow: TextOverflow.ellipsis),
                  ),
                ]),
              ),
            const SizedBox(height: FwLayout.s2),
            Row(children: [
              VerdictPill('graph ${_receipt?['graph_id'] ?? ''}',
                  status: 'verified'),
              if ((_receipt?['cache_hits'] ?? 0) != 0)
                Padding(
                    padding: const EdgeInsets.only(left: FwLayout.s2),
                    child: VerdictPill('${_receipt?['cache_hits']} cached',
                        status: 'verified')),
              const Spacer(),
              OutlinedButton(
                  onPressed: _exportSpec, child: const Text('.fwgraph')),
              const SizedBox(width: FwLayout.s2),
              OutlinedButton(
                  onPressed: _save, child: const Text('Save sinks')),
            ]),
            if (_savedTo != null) ...[
              const SizedBox(height: FwLayout.s2),
              Row(children: [
                const VerdictPill('saved', status: 'verified'),
                const SizedBox(width: FwLayout.s2),
                Expanded(
                    child: Text(_savedTo!,
                        style: fwMono(t, size: 11).copyWith(color: t.inkMuted),
                        overflow: TextOverflow.ellipsis)),
              ]),
            ],
          ],
        ],
      ),
    );
  }
}
