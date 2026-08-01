// charts.dart — quantitative marks in the same hairline language as the
// rest of the surface: a proportional bar and a sparkline. Verdict tints
// only; no chart library, no decoration.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';

/// A thin horizontal proportion bar (0..1), verdict-tinted.
class MiniBar extends StatelessWidget {
  final double fraction;
  final String status;
  final double width;
  const MiniBar(this.fraction,
      {super.key, this.status = 'verified', this.width = 90});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final c = t.statusColor(status);
    return Container(
      width: width,
      height: 6,
      decoration: BoxDecoration(
        color: t.ground2,
        borderRadius: BorderRadius.circular(3),
        border: Border.all(color: t.hairline, width: 0.5),
      ),
      alignment: Alignment.centerLeft,
      child: FractionallySizedBox(
        widthFactor: fraction.clamp(0.0, 1.0),
        child: Container(
          decoration: BoxDecoration(
            color: c.withValues(alpha: 0.75),
            borderRadius: BorderRadius.circular(3),
          ),
        ),
      ),
    );
  }
}

/// A small polyline sparkline over raw values; flat honest baseline when
/// there is nothing to show.
class Sparkline extends StatelessWidget {
  final List<double> values;
  final double width;
  final double height;
  final String status;
  const Sparkline(this.values,
      {super.key, this.width = 120, this.height = 28, this.status = 'verified'});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return CustomPaint(
      size: Size(width, height),
      painter: _SparkPainter(
          values: values, line: t.statusColor(status), hair: t.hairline),
    );
  }
}

class _SparkPainter extends CustomPainter {
  final List<double> values;
  final Color line;
  final Color hair;
  _SparkPainter({required this.values, required this.line, required this.hair});

  @override
  void paint(Canvas canvas, Size size) {
    final base = Paint()
      ..color = hair
      ..strokeWidth = 1;
    canvas.drawLine(Offset(0, size.height - 1),
        Offset(size.width, size.height - 1), base);
    if (values.length < 2) return;
    final lo = values.reduce((a, b) => a < b ? a : b);
    final hi = values.reduce((a, b) => a > b ? a : b);
    final span = (hi - lo).abs() < 1e-9 ? 1.0 : hi - lo;
    final path = Path();
    for (var i = 0; i < values.length; i++) {
      final x = i / (values.length - 1) * size.width;
      final y = size.height - 3 - ((values[i] - lo) / span) * (size.height - 6);
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    canvas.drawPath(
        path,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.4
          ..color = line);
  }

  @override
  bool shouldRepaint(_SparkPainter old) =>
      old.values != values || old.line != line;
}
