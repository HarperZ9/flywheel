// pipeline_panel.dart — the creative line: ordered stages from source
// through the lane's kernels into treatments, the image flowing stage to
// stage while every stage hash folds into a chain. Build the line, run
// it, read the trail, keep the still.

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

const _sources = ['plate', 'wireframe', 'harmonograph'];
const _transforms = ['dither', 'pixel_sort', 'film_frame'];
const _primitives = ['cube', 'pyramid', 'orbit-sphere', 'horizon'];

class PipelinePanel extends StatefulWidget {
  final GatewayClient client;
  const PipelinePanel({super.key, required this.client});

  @override
  State<PipelinePanel> createState() => _PipelinePanelState();
}

class _PipelinePanelState extends State<PipelinePanel> {
  final _seed = TextEditingController(text: '58');
  final _title = TextEditingController(text: 'order out of disorder');
  final List<Map<String, dynamic>> _stages = [
    {'op': 'wireframe', 'primitive': 'orbit-sphere'},
    {'op': 'dither', 'levels': 3},
    {'op': 'film_frame'},
  ];
  Uint8List? _png;
  Map<String, dynamic>? _receipt;
  bool _busy = false;
  String? _error, _savedTo;

  @override
  void dispose() {
    _seed.dispose();
    _title.dispose();
    super.dispose();
  }

  List<Map<String, dynamic>> _specs() {
    final seed = int.tryParse(_seed.text.trim()) ?? 58;
    return [
      for (final s in _stages)
        {
          'op': s['op'],
          'args': {
            'seed': seed,
            'width': 640,
            'height': 400,
            if (s['op'] == 'wireframe') 'primitive': s['primitive'],
            if (s['op'] == 'dither') 'levels': s['levels'],
            if (s['op'] == 'film_frame') 'title': _title.text.trim(),
            if (s['op'] == 'film_frame') 'subtitle': 'zentropy labs',
          },
        },
    ];
  }

  Future<void> _run() async {
    if (_busy || _stages.isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
      _savedTo = null;
    });
    try {
      final r = await widget.client.studioPipeline(_specs());
      if (!mounted) return;
      setState(() {
        if (r['refused'] == true || r['error'] != null) {
          _error = (r['refusals'] is List && (r['refusals'] as List).isNotEmpty)
              ? '${(r['refusals'] as List).first}'
              : '${r['error'] ?? 'refused'}';
          _png = null;
        } else {
          _png = base64Decode('${r['png_b64']}');
          _receipt = r['receipt'] as Map<String, dynamic>?;
        }
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _save() async {
    final png = _png;
    final rc = _receipt;
    if (png == null || rc == null) return;
    try {
      final home = Platform.environment['USERPROFILE'] ??
          Platform.environment['HOME'] ??
          '.';
      final f = File('$home${Platform.pathSeparator}Downloads'
          '${Platform.pathSeparator}line-${rc['pipeline_id']}.png');
      f.writeAsBytesSync(png);
      setState(() => _savedTo = f.path);
    } catch (e) {
      setState(() => _error = 'save failed: $e');
    }
  }

  void _cycle(int i) {
    final s = _stages[i];
    setState(() {
      if (s['op'] == 'wireframe') {
        final n = _primitives.indexOf('${s['primitive']}');
        s['primitive'] = _primitives[(n + 1) % _primitives.length];
      } else if (s['op'] == 'dither') {
        s['levels'] = (s['levels'] as int) % 4 + 2; // 2..5
      }
    });
  }

  String _chipLabel(Map<String, dynamic> s) {
    if (s['op'] == 'wireframe') return 'wireframe · ${s['primitive']}';
    if (s['op'] == 'dither') return 'dither · ${s['levels']}';
    return '${s['op']}';
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
              'A source starts the line, the lane\'s kernels bend it, the '
              'film treatment finishes it. Every stage hash folds into the '
              'chain, so the pipeline id witnesses the whole line in order. '
              'Tap a stage to vary it.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          Wrap(
            spacing: FwLayout.s2,
            runSpacing: FwLayout.s2,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              for (var i = 0; i < _stages.length; i++)
                InputChip(
                  label: Text(_chipLabel(_stages[i]),
                      style: fwMono(t, size: 11.5)),
                  onPressed: () => _cycle(i),
                  onDeleted: () => setState(() => _stages.removeAt(i)),
                ),
              PopupMenuButton<String>(
                tooltip: 'Add a stage',
                itemBuilder: (_) => [
                  for (final op in [..._sources, ..._transforms])
                    PopupMenuItem(value: op, child: Text(op)),
                ],
                onSelected: (op) => setState(() => _stages.add({
                      'op': op,
                      if (op == 'wireframe') 'primitive': 'cube',
                      if (op == 'dither') 'levels': 3,
                    })),
                child: Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: FwLayout.s3, vertical: FwLayout.s2),
                  decoration: BoxDecoration(
                      border: Border.all(color: t.hairline),
                      borderRadius: BorderRadius.circular(16)),
                  child: Text('+ stage', style: fwMono(t, size: 11.5)),
                ),
              ),
            ],
          ),
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            SizedBox(
              width: 80,
              child: TextField(
                controller: _seed,
                style: fwMono(t, size: 12),
                decoration: const InputDecoration(hintText: 'seed'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            Expanded(
              child: TextField(
                controller: _title,
                style: const TextStyle(fontSize: 12.5),
                decoration: const InputDecoration(
                    hintText: 'film title (lowercase face)'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            FilledButton(
              onPressed: _busy ? null : _run,
              child: Text(_busy ? 'Running…' : 'Run the line'),
            ),
          ]),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s2),
            HonestNull(_error!),
          ],
          if (_png != null) ...[
            const SizedBox(height: FwLayout.s3),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 360),
              child: Image.memory(_png!,
                  fit: BoxFit.contain, filterQuality: FilterQuality.none),
            ),
            const SizedBox(height: FwLayout.s2),
            for (final s in ((_receipt?['stages'] as List?) ?? const []))
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: Row(children: [
                  const VerdictDot('verified'),
                  const SizedBox(width: FwLayout.s2),
                  Expanded(
                    child: Text(
                        '${(s as Map)['op']}'
                        '${s['kernel_receipt_hash'] != null ? '  ·  lane ${s['kernel_receipt_hash']}' : ''}'
                        '  ·  chain ${s['chain']}',
                        style: fwMono(t, size: 11)
                            .copyWith(color: t.inkMuted),
                        overflow: TextOverflow.ellipsis),
                  ),
                ]),
              ),
            const SizedBox(height: FwLayout.s2),
            Row(children: [
              VerdictPill('line ${_receipt?['pipeline_id'] ?? ''}',
                  status: 'verified'),
              const Spacer(),
              OutlinedButton(onPressed: _save, child: const Text('Save PNG')),
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
