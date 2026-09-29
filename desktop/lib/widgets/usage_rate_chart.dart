import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../models/usage_live_models.dart';
import '../theme/flywheel_theme.dart';

/// Custom, time-scaled history. Missing observations break the line.
class UsageRateChart extends StatelessWidget {
  final List<UsageRatePoint> points;
  final bool prefill;
  const UsageRateChart({super.key, required this.points, this.prefill = false});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final values = points.map((p) => prefill ? p.prefill : p.decode);
    final measured = values.whereType<double>().toList();
    final peak = measured.isEmpty ? null : measured.fold<double>(0, math.max);
    final label = prefill ? 'Prompt processing' : 'Generation';
    final latest = points.isEmpty
        ? null
        : (prefill ? points.last.prefill : points.last.decode);
    return Semantics(
      label: '$label history. Latest ${usageRate(latest)}. '
          'Peak ${usageRate(peak)}. Missing samples are gaps.',
      child: ExcludeSemantics(
          child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(spacing: 16, runSpacing: 4, children: [
            Text(label, style: fwMono(t, size: 12, color: t.inkSoft)),
            Text(usageRate(latest), style: fwMono(t, size: 12, color: t.ink)),
          ]),
          const SizedBox(height: 8),
          SizedBox(
              height: 82,
              width: double.infinity,
              child: CustomPaint(
                  painter:
                      _RatePainter(points, prefill, t.inkMuted, t.hairline))),
          const SizedBox(height: 4),
          Text(
              points
                          .where(
                              (p) => (prefill ? p.prefill : p.decode) != null)
                          .length <
                      2
                  ? 'Waiting for a second measured sample'
                  : 'Recent 60 samples · peak ${usageRate(peak)}',
              style: fwMono(t, size: 10, color: t.inkMuted)),
        ],
      )),
    );
  }
}

class _RatePainter extends CustomPainter {
  final List<UsageRatePoint> points;
  final bool prefill;
  final Color ink, grid;
  _RatePainter(this.points, this.prefill, this.ink, this.grid);

  @override
  void paint(Canvas canvas, Size size) {
    final line = Paint()
      ..color = grid
      ..strokeWidth = 1;
    for (var i = 0; i <= 2; i++) {
      final y = 1 + (size.height - 2) * i / 2;
      canvas.drawLine(Offset(0, y), Offset(size.width, y), line);
    }
    if (points.isEmpty) return;
    final values = points.map((p) => prefill ? p.prefill : p.decode).toList();
    final peak =
        math.max(1.0, values.whereType<double>().fold<double>(0, math.max));
    final end = points.last.time.millisecondsSinceEpoch;
    final start =
        math.min(end - 60000, points.first.time.millisecondsSinceEpoch);
    final path = Path();
    var connected = false;
    for (var i = 0; i < points.length; i++) {
      final v = values[i];
      if (v == null) {
        connected = false;
        continue;
      }
      final x = (points[i].time.millisecondsSinceEpoch - start) /
          (end - start) *
          size.width;
      final y = size.height - 2 - v / peak * (size.height - 4);
      if (connected) {
        path.lineTo(x, y);
      } else {
        path.moveTo(x, y);
      }
      canvas.drawCircle(Offset(x, y), 1.8, Paint()..color = ink);
      connected = true;
    }
    canvas.drawPath(
        path,
        Paint()
          ..color = ink
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.5);
  }

  @override
  bool shouldRepaint(covariant _RatePainter old) =>
      old.points != points ||
      old.prefill != prefill ||
      old.ink != ink ||
      old.grid != grid;
}
