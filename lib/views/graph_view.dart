// graph_view.dart — the Graph view: the platform composition drawn from
// live state. Flywheel at the center, lanes on the inner ring colored by
// their live verdict, the wider spine on the outer ring. Drawn from
// /api/lanes and /api/world on every build; there is no stale diagram to
// drift from.

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class GraphView extends StatelessWidget {
  final WorldDoc? world;
  final LaneRoster? roster;
  final bool alive;
  const GraphView({super.key, this.world, this.roster, required this.alive});

  @override
  Widget build(BuildContext context) {
    if (!alive) {
      return const FwEmpty(
          'The engine is offline. The graph draws from live state.',
          command: 'flywheel up');
    }
    if (roster == null) {
      return const Center(child: CircularProgressIndicator(strokeWidth: 2));
    }
    final t = context.fw;
    final lanes = roster!.lanes;
    final laneNames = lanes.map((l) => l.name).toSet();
    final outer = (world?.spine?.flagships ?? const <String>[])
        .where((f) => !laneNames.contains(f) && f != 'flywheel')
        .toList();
    return ViewScroll(
      children: [
        const SectionHeader('Graph', kicker: 'the composition, live'),
        const SizedBox(height: FwLayout.s3),
        Text(
          'One platform, every engine a node. Inner ring: the installed '
          'lanes, colored by their live verdict. Outer ring: the wider '
          'family the spine names. Redrawn from the engine on every poll.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: FwLayout.s4),
        HairlineCard(
          padding: EdgeInsets.zero,
          child: SizedBox(
            height: 460,
            width: double.infinity,
            child: RepaintBoundary(
              child: CustomPaint(
                painter: _GraphPainter(tokens: t, lanes: lanes, outer: outer),
              ),
            ),
          ),
        ),
        const SizedBox(height: FwLayout.s3),
        Row(
          children: [
            const VerdictDot('live', size: 7),
            const SizedBox(width: 4),
            Text('live', style: fwMono(t, size: 10.5, color: t.inkMuted)),
            const SizedBox(width: FwLayout.s3),
            const VerdictDot('declared', size: 7),
            const SizedBox(width: 4),
            Text('declared, unprobed',
                style: fwMono(t, size: 10.5, color: t.inkMuted)),
            const SizedBox(width: FwLayout.s3),
            const VerdictDot('missing', size: 7),
            const SizedBox(width: 4),
            Text('missing or stale',
                style: fwMono(t, size: 10.5, color: t.inkMuted)),
          ],
        ),
      ],
    );
  }
}

class _GraphPainter extends CustomPainter {
  final FwTokens tokens;
  final List<Lane> lanes;
  final List<String> outer;
  _GraphPainter({required this.tokens, required this.lanes, required this.outer});

  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    final rInner = size.shortestSide * 0.28;
    final rOuter = size.shortestSide * 0.44;
    final edge = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..color = tokens.line;

    // Outer family first (behind), faint.
    final outerPts = _ring(c, rOuter, outer.length, offset: 0.5);
    for (var i = 0; i < outer.length; i++) {
      canvas.drawLine(c, outerPts[i], edge..color = tokens.hairline);
      _node(canvas, outerPts[i], 5, tokens.unverifiable.withValues(alpha: 0.5));
      _label(canvas, outerPts[i], c, outer[i], tokens.inkFaint, 10);
    }

    // Lanes on the inner ring, verdict-colored.
    final lanePts = _ring(c, rInner, lanes.length);
    for (var i = 0; i < lanes.length; i++) {
      canvas.drawLine(c, lanePts[i], edge..color = tokens.line);
      final color = tokens.statusColor(lanes[i].status);
      _node(canvas, lanePts[i], 7, color);
      _label(canvas, lanePts[i], c, lanes[i].name, tokens.inkSoft, 11.5);
    }

    // The hub.
    canvas.drawCircle(
        c, 13, Paint()..color = tokens.drift.withValues(alpha: 0.14));
    canvas.drawCircle(
        c,
        13,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.4
          ..color = tokens.drift);
    _text(canvas, 'flywheel', c + const Offset(0, 22), tokens.ink, 12,
        FontWeight.w700, center: true);
  }

  List<Offset> _ring(Offset c, double r, int n, {double offset = 0}) {
    return [
      for (var i = 0; i < n; i++)
        c +
            Offset.fromDirection(
                -math.pi / 2 + 2 * math.pi * (i + offset) / math.max(n, 1), r),
    ];
  }

  void _node(Canvas canvas, Offset p, double r, Color color) {
    canvas.drawCircle(p, r, Paint()..color = color.withValues(alpha: 0.18));
    canvas.drawCircle(p, r * 0.55, Paint()..color = color);
  }

  void _label(Canvas canvas, Offset p, Offset c, String text, Color color,
      double fontSize) {
    final away = (p - c);
    final dir = away.distance == 0 ? const Offset(0, 1) : away / away.distance;
    _text(canvas, text, p + dir * 16, color, fontSize, FontWeight.w500,
        center: true);
  }

  void _text(Canvas canvas, String s, Offset at, Color color, double fontSize,
      FontWeight weight,
      {bool center = false}) {
    final tp = TextPainter(
      text: TextSpan(
          text: s,
          style: TextStyle(
              color: color,
              fontSize: fontSize,
              fontWeight: weight,
              fontFamily: kMonoFamily)),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas,
        center ? at - Offset(tp.width / 2, tp.height / 2) : at);
  }

  @override
  bool shouldRepaint(_GraphPainter old) =>
      old.lanes != lanes || old.outer != outer || old.tokens != tokens;
}
