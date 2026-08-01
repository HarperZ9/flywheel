// raster_fx_panel.dart — the telos raster kernels over the seeded plate:
// ordered dither and pixel-sort, run by the lane's own module, with the
// kernel's own hashes on the receipt and a PNG export.

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class RasterFxPanel extends StatefulWidget {
  final GatewayClient client;
  const RasterFxPanel({super.key, required this.client});

  @override
  State<RasterFxPanel> createState() => _RasterFxPanelState();
}

class _RasterFxPanelState extends State<RasterFxPanel> {
  String _kernel = 'raster.ordered-dither';
  final _seed = TextEditingController(text: '58');
  String _ground = 'dark';
  double _levels = 3, _matrix = 8, _threshold = 96;
  Uint8List? _png;
  Map<String, dynamic>? _receipt, _measurement;
  bool _busy = false;
  String? _error, _savedTo;

  @override
  void dispose() {
    _seed.dispose();
    super.dispose();
  }

  Future<void> _apply() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _savedTo = null;
    });
    try {
      final r = await widget.client.telosRaster(
        _kernel,
        source: {
          'kind': 'plate',
          'seed': int.tryParse(_seed.text.trim()) ?? 58,
          'ground': _ground,
          'width': 480,
          'height': 300,
        },
        args: _kernel == 'raster.ordered-dither'
            ? {'levels': _levels.round(), 'matrixSize': _matrix.round()}
            : {'threshold': _threshold.round()},
      );
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
          _measurement = r['measurement'] as Map<String, dynamic>?;
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
    if (png == null) return;
    try {
      final home = Platform.environment['USERPROFILE'] ??
          Platform.environment['HOME'] ??
          '.';
      final short = _kernel.split('.').last;
      final f = File('$home${Platform.pathSeparator}Downloads'
          '${Platform.pathSeparator}telos-$short-${_seed.text.trim()}.png');
      f.writeAsBytesSync(png);
      setState(() => _savedTo = f.path);
    } catch (e) {
      setState(() => _error = 'save failed: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final dither = _kernel == 'raster.ordered-dither';
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
              'The lane\'s dither and pixel-sort, run over the seeded plate '
              'by the kernel module itself. The receipt carries the '
              'kernel\'s own hashes beside the png hash you can re-check.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            DropdownButton<String>(
              value: _kernel,
              isDense: true,
              style: fwMono(t, size: 11.5).copyWith(color: t.ink),
              items: const [
                DropdownMenuItem(
                    value: 'raster.ordered-dither', child: Text('dither')),
                DropdownMenuItem(
                    value: 'raster.pixel-sort-rows',
                    child: Text('pixel-sort')),
              ],
              onChanged: (v) =>
                  setState(() => _kernel = v ?? 'raster.ordered-dither'),
            ),
            const SizedBox(width: FwLayout.s3),
            DropdownButton<String>(
              value: _ground,
              isDense: true,
              style: fwMono(t, size: 11.5).copyWith(color: t.ink),
              items: const [
                DropdownMenuItem(value: 'dark', child: Text('dark')),
                DropdownMenuItem(value: 'ceramic', child: Text('ceramic')),
              ],
              onChanged: (v) => setState(() => _ground = v ?? 'dark'),
            ),
            const SizedBox(width: FwLayout.s3),
            SizedBox(
              width: 80,
              child: TextField(
                controller: _seed,
                style: fwMono(t, size: 12),
                decoration: const InputDecoration(hintText: 'seed'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            if (dither) ...[
              Expanded(
                child: _knob(t, 'levels', _levels, 2, 8,
                    (v) => _levels = v.roundToDouble()),
              ),
              Expanded(
                child: _knob(t, 'matrix', _matrix, 2, 16,
                    (v) => _matrix = _pow2(v)),
              ),
            ] else
              Expanded(
                child: _knob(t, 'threshold', _threshold, 32, 224,
                    (v) => _threshold = v.roundToDouble()),
              ),
            const SizedBox(width: FwLayout.s3),
            FilledButton(
              onPressed: _busy ? null : _apply,
              child: Text(_busy ? 'Running…' : 'Apply'),
            ),
          ]),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s2),
            HonestNull(_error!),
          ],
          if (_png != null) ...[
            const SizedBox(height: FwLayout.s3),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 320),
              child: Image.memory(_png!,
                  fit: BoxFit.contain, filterQuality: FilterQuality.none),
            ),
            const SizedBox(height: FwLayout.s2),
            Row(children: [
              if (dither)
                VerdictPill('${_measurement?['unique_levels'] ?? '?'} levels',
                    status: 'verified')
              else
                const VerdictPill('sorted', status: 'verified'),
              const SizedBox(width: FwLayout.s2),
              Expanded(
                child: HashText('kernel receipt',
                    '${_receipt?['kernel_receipt_hash'] ?? ''}', keep: 18),
              ),
              Expanded(
                child: HashText(
                    'png', '${_receipt?['png_sha256'] ?? ''}', keep: 16),
              ),
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

  double _pow2(double v) {
    final n = v.round();
    if (n <= 2) return 2;
    if (n <= 5) return 4;
    if (n <= 11) return 8;
    return 16;
  }

  Widget _knob(FwTokens t, String label, double value, double min, double max,
      void Function(double) set) {
    return Row(children: [
      Text(label, style: fwMono(t, size: 11, color: t.inkFaint)),
      Expanded(
        child: Slider(
          value: value.clamp(min, max),
          min: min,
          max: max,
          onChanged: (v) => setState(() => set(v)),
        ),
      ),
      Text('${value.round()}', style: fwMono(t, size: 11, color: t.inkMuted)),
    ]);
  }
}
