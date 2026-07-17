// harmonograph_panel.dart — the telos engine's plotter kernel, driven in
// place: the curve is computed by the lane's own module, the receipt
// hashes are the kernel's own, and the SVG export is a plotter-ready
// path. Composition, not reimplementation.

import 'dart:io';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class HarmonographPanel extends StatefulWidget {
  final GatewayClient client;
  const HarmonographPanel({super.key, required this.client});

  @override
  State<HarmonographPanel> createState() => _HarmonographPanelState();
}

class _HarmonographPanelState extends State<HarmonographPanel> {
  double _fx = 3, _fy = 4, _phase = 1.57, _damping = 0.004;
  double _samples = 900;
  List<Offset> _points = [];
  Map<String, dynamic>? _result;
  bool _busy = false;
  String? _error, _savedTo;

  Future<void> _draw() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _savedTo = null;
    });
    try {
      final r = await widget.client.telosKernel('plotter.harmonograph-path', {
        'samples': _samples.round(),
        'x': {'frequency': _fx.round(), 'damping': _damping},
        'y': {
          'frequency': _fy.round(),
          'phase': _phase,
          'damping': _damping * 1.1
        },
      });
      if (!mounted) return;
      setState(() {
        if (r['error'] != null) {
          _error = '${r['error']}';
          _points = [];
          _result = null;
        } else {
          _result = r['result'] as Map<String, dynamic>?;
          _points = [
            for (final p in (_result?['points'] as List? ?? const []))
              Offset(((p as Map)['x'] as num).toDouble(),
                  (p['y'] as num).toDouble())
          ];
        }
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _saveSvg() async {
    if (_points.isEmpty) return;
    try {
      final d = StringBuffer('M ');
      for (var i = 0; i < _points.length; i++) {
        final p = _points[i];
        d.write('${(p.dx * 400 + 500).toStringAsFixed(2)} '
            '${(p.dy * -400 + 500).toStringAsFixed(2)} ');
        if (i == 0) d.write('L ');
      }
      final svg = '<svg xmlns="http://www.w3.org/2000/svg" '
          'viewBox="0 0 1000 1000">'
          '<path d="$d" fill="none" stroke="#0B0C0E" stroke-width="1.2"/>'
          '</svg>';
      final home = Platform.environment['USERPROFILE'] ??
          Platform.environment['HOME'] ??
          '.';
      final f = File('$home${Platform.pathSeparator}Downloads'
          '${Platform.pathSeparator}harmonograph-${_fx.round()}-'
          '${_fy.round()}.svg');
      f.writeAsStringSync(svg);
      setState(() => _savedTo = f.path);
    } catch (e) {
      setState(() => _error = 'save failed: $e');
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
              'The damped curve a pen plotter draws: computed by the telos '
              'engine\'s own kernel module, returned with its own receipt '
              'hashes. The SVG export is a plotter-ready path.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            _knob(t, 'fx', _fx, 1, 9, (v) => _fx = v.roundToDouble()),
            _knob(t, 'fy', _fy, 1, 9, (v) => _fy = v.roundToDouble()),
            _knob(t, 'phase', _phase, 0, 3.14, (v) => _phase = v),
          ]),
          Row(children: [
            _knob(t, 'damping', _damping, 0.001, 0.02, (v) => _damping = v),
            _knob(t, 'samples', _samples, 200, 2400,
                (v) => _samples = v.roundToDouble()),
            FilledButton(
              onPressed: _busy ? null : _draw,
              child: Text(_busy ? 'Drawing…' : 'Draw'),
            ),
          ]),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s2),
            HonestNull(_error!),
          ],
          if (_points.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s3),
            SizedBox(
              height: 320,
              width: double.infinity,
              child: CustomPaint(
                painter: _PathPainter(_points, t.ink),
              ),
            ),
            const SizedBox(height: FwLayout.s2),
            Row(children: [
              const VerdictPill('drawn by the lane', status: 'verified'),
              const SizedBox(width: FwLayout.s2),
              Expanded(
                child: HashText(
                    'receipt', '${_result?['receipt_hash'] ?? ''}', keep: 20),
              ),
              OutlinedButton(
                  onPressed: _saveSvg, child: const Text('Save SVG')),
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

  Widget _knob(FwTokens t, String label, double value, double min, double max,
      void Function(double) set) {
    return Expanded(
      child: Row(children: [
        SizedBox(
          width: 62,
          child: Text(label, style: fwMono(t, size: 11, color: t.inkFaint)),
        ),
        Expanded(
          child: Slider(
            value: value.clamp(min, max),
            min: min,
            max: max,
            onChanged: (v) => setState(() => set(v)),
            onChangeEnd: (_) => _draw(),
          ),
        ),
        SizedBox(
          width: 52,
          child: Text(
              value >= 10 ? value.round().toString()
                  : value.toStringAsFixed(3),
              style: fwMono(t, size: 11, color: t.inkMuted)),
        ),
      ]),
    );
  }
}

class _PathPainter extends CustomPainter {
  final List<Offset> points;
  final Color ink;
  _PathPainter(this.points, this.ink);

  @override
  void paint(Canvas canvas, Size size) {
    if (points.length < 2) return;
    final s = size.shortestSide * 0.46;
    final c = Offset(size.width / 2, size.height / 2);
    final path = Path()
      ..moveTo(c.dx + points.first.dx * s, c.dy - points.first.dy * s);
    for (final p in points.skip(1)) {
      path.lineTo(c.dx + p.dx * s, c.dy - p.dy * s);
    }
    canvas.drawPath(
        path,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.1
          ..color = ink.withValues(alpha: 0.85));
  }

  @override
  bool shouldRepaint(_PathPainter old) =>
      old.points != points || old.ink != ink;
}
