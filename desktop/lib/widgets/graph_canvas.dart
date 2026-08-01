// graph_canvas.dart — the knowledge graph drawn as a deterministic radial
// layout: the hub at center, each kind on its ring, node SIZE encoding the
// engine-computed priority and SHAPE encoding the kind. Color stays a
// verdict. The tapped node carries the view's one hot ring; nodes inside
// the current context plan carry a verified ring.

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models/graph_models.dart';
import '../theme/flywheel_theme.dart';

const _ringByKind = {
  'hub': 0.0,
  'lane': 0.30,
  'project': 0.48,
  'memory': 0.48,
  'plugin': 0.66,
  'workflow': 0.66,
  'error': 0.82,
};

/// Deterministic positions: nodes share their kind's ring, spread evenly
/// in sorted-id order so the same graph always draws the same picture.
Map<String, Offset> graphPositions(List<GraphNode> nodes, Size size) {
  final c = size.center(Offset.zero);
  final r = size.shortestSide / 2 - 34;
  final byRing = <double, List<GraphNode>>{};
  for (final n in nodes) {
    byRing.putIfAbsent(_ringByKind[n.kind] ?? 0.9, () => []).add(n);
  }
  final out = <String, Offset>{};
  for (final entry in byRing.entries) {
    final ring = entry.value..sort((a, b) => a.id.compareTo(b.id));
    for (var i = 0; i < ring.length; i++) {
      out[ring[i].id] = entry.key == 0.0
          ? c
          : c +
              Offset.fromDirection(
                  -math.pi / 2 + 2 * math.pi * i / ring.length,
                  r * entry.key);
    }
  }
  return out;
}

String statusOf(GraphNode n) => switch (n.verdict) {
      'enabled' => 'live',
      'disabled' => 'missing',
      'error' => 'drift',
      _ => n.verdict,
    };

class GraphCanvas extends StatelessWidget {
  final KnowledgeGraph graph;
  final String? selectedId;
  final ValueChanged<GraphNode?> onSelect;
  const GraphCanvas(
      {super.key,
      required this.graph,
      this.selectedId,
      required this.onSelect});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return LayoutBuilder(builder: (context, constraints) {
      final size = Size(constraints.maxWidth, constraints.maxHeight);
      final pos = graphPositions(graph.nodes, size);
      return GestureDetector(
        onTapUp: (d) {
          GraphNode? hit;
          for (final n in graph.nodes) {
            final p = pos[n.id];
            if (p != null && (p - d.localPosition).distance < 16) hit = n;
          }
          onSelect(hit);
        },
        child: CustomPaint(
          size: size,
          painter: _KnowledgeGraphPainter(
              tokens: t,
              graph: graph,
              positions: pos,
              selectedId: selectedId),
        ),
      );
    });
  }
}

class _KnowledgeGraphPainter extends CustomPainter {
  final FwTokens tokens;
  final KnowledgeGraph graph;
  final Map<String, Offset> positions;
  final String? selectedId;
  _KnowledgeGraphPainter(
      {required this.tokens,
      required this.graph,
      required this.positions,
      this.selectedId});

  @override
  void paint(Canvas canvas, Size size) {
    final edge = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..color = tokens.hairline;
    for (final e in graph.edges) {
      final a = positions[e.from], b = positions[e.to];
      if (a != null && b != null) canvas.drawLine(a, b, edge);
    }
    final planIds = graph.plan?.selectedIds ?? const <String>{};
    for (final n in graph.nodes) {
      final p = positions[n.id];
      if (p == null) continue;
      final color = tokens.statusColor(statusOf(n));
      final radius = 5.0 + math.min(6.0, n.priority * 2.5);
      if (planIds.contains(n.id)) {
        canvas.drawCircle(
            p,
            radius + 5,
            Paint()
              ..style = PaintingStyle.stroke
              ..strokeWidth = 1.2
              ..color = tokens.verified.withValues(alpha: 0.7));
      }
      if (n.id == selectedId) {
        canvas.drawCircle(
            p,
            radius + 8,
            Paint()
              ..style = PaintingStyle.stroke
              ..strokeWidth = 1.4
              ..color = tokens.drift);
      }
      _shape(canvas, n.kind, p, radius, color);
      final labelColor =
          n.kind == 'hub' ? tokens.ink : tokens.inkSoft;
      _text(canvas, n.label, p + Offset(0, radius + 12), labelColor,
          n.kind == 'hub' ? 12 : 10.5,
          n.kind == 'hub' ? FontWeight.w700 : FontWeight.w500);
    }
  }

  void _shape(Canvas canvas, String kind, Offset p, double r, Color color) {
    final fill = Paint()..color = color.withValues(alpha: 0.20);
    final core = Paint()..color = color;
    switch (kind) {
      case 'project': // square: a place work lives in
        canvas.drawRect(Rect.fromCircle(center: p, radius: r), fill);
        canvas.drawRect(Rect.fromCircle(center: p, radius: r * 0.55), core);
      case 'memory': // diamond
        canvas.save();
        canvas.translate(p.dx, p.dy);
        canvas.rotate(math.pi / 4);
        canvas.drawRect(
            Rect.fromCircle(center: Offset.zero, radius: r), fill);
        canvas.drawRect(
            Rect.fromCircle(center: Offset.zero, radius: r * 0.55), core);
        canvas.restore();
      case 'plugin': // triangle
        final path = Path()
          ..moveTo(p.dx, p.dy - r)
          ..lineTo(p.dx + r, p.dy + r * 0.8)
          ..lineTo(p.dx - r, p.dy + r * 0.8)
          ..close();
        canvas.drawPath(path, fill..color = color.withValues(alpha: 0.35));
        canvas.drawCircle(p, r * 0.3, core);
      case 'error': // an X: the blind spot stays loud
        final s = Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2
          ..color = color;
        canvas.drawLine(p + Offset(-r, -r), p + Offset(r, r), s);
        canvas.drawLine(p + Offset(-r, r), p + Offset(r, -r), s);
      default: // hub, lane, workflow: circles
        canvas.drawCircle(p, r, fill);
        canvas.drawCircle(p, r * 0.55, core);
    }
  }

  void _text(Canvas canvas, String s, Offset at, Color color, double size,
      FontWeight weight) {
    final tp = TextPainter(
      text: TextSpan(
          text: s,
          style: TextStyle(
              color: color,
              fontSize: size,
              fontWeight: weight,
              fontFamily: kMonoFamily)),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, at - Offset(tp.width / 2, tp.height / 2));
  }

  @override
  bool shouldRepaint(_KnowledgeGraphPainter old) =>
      old.graph != graph ||
      old.selectedId != selectedId ||
      old.tokens != tokens;
}
