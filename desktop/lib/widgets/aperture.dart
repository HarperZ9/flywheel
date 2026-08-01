// aperture.dart — the Flywheel brand mark: a seeded generative aperture.
//
// Same family as the site mark (telos-v2 scripts/gen-mark.mjs, seed 58,
// mulberry32 PRNG): a dithered corona of ink dots around a void core, with
// one verified-green flare arc. Deterministic — the same seed always draws
// the same mark. The spectrum stays out of UI chrome; ink + one verdict
// color only.

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';

const kApertureSeed = 58;

/// mulberry32 — the same tiny PRNG the web mark uses, so the draw is
/// reproducible from the recorded seed.
class Mulberry32 {
  int _state;
  Mulberry32(int seed) : _state = seed & 0xFFFFFFFF;

  double next() {
    _state = (_state + 0x6D2B79F5) & 0xFFFFFFFF;
    int t = _state;
    t = _imul(t ^ (t >> 15), t | 1);
    t ^= (t + _imul(t ^ (t >> 7), t | 61)) & 0xFFFFFFFF;
    return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0;
  }

  static int _imul(int a, int b) {
    final al = a & 0xFFFF, ah = (a >> 16) & 0xFFFF;
    final bl = b & 0xFFFF, bh = (b >> 16) & 0xFFFF;
    return (al * bl + (((ah * bl + al * bh) << 16) & 0xFFFFFFFF)) & 0xFFFFFFFF;
  }
}

class ApertureMark extends StatelessWidget {
  final double size;
  const ApertureMark({super.key, this.size = 32});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return RepaintBoundary(
      child: CustomPaint(
        size: Size.square(size),
        painter: _AperturePainter(ink: t.ink, flare: t.verified),
      ),
    );
  }
}

class _AperturePainter extends CustomPainter {
  final Color ink;
  final Color flare;
  _AperturePainter({required this.ink, required this.flare});

  @override
  void paint(Canvas canvas, Size size) {
    final rng = Mulberry32(kApertureSeed);
    final c = size.center(Offset.zero);
    final r = size.shortestSide / 2;
    final dot = Paint()..style = PaintingStyle.fill;

    // Dithered corona: dots sampled in polar space, density peaking mid-band
    // around the void core, thinning to transparent edges.
    const n = 420;
    for (var i = 0; i < n; i++) {
      final angle = rng.next() * 2 * math.pi;
      // Bias radius toward the band center (0.62 r).
      final u = rng.next();
      final radial = 0.34 + 0.66 * math.sqrt(u);
      final dist = radial * r;
      final band = 1.0 - ((radial - 0.62).abs() / 0.38).clamp(0.0, 1.0);
      final keep = rng.next() < band * band * 1.35;
      if (!keep) continue;
      final alpha = (0.25 + 0.65 * band) * (0.55 + 0.45 * rng.next());
      dot.color = ink.withValues(alpha: alpha.clamp(0.0, 1.0));
      final dotR = (0.014 + 0.020 * band) * r * (0.6 + 0.5 * rng.next());
      canvas.drawCircle(
          c + Offset(math.cos(angle) * dist, math.sin(angle) * dist), dotR, dot);
    }

    // The one flare: a short verified arc on the band, angle drawn from the
    // same PRNG stream so it is part of the seeded composition.
    final flareStart = rng.next() * 2 * math.pi;
    final flareSweep = 0.5 + rng.next() * 0.5;
    final arc = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = math.max(1.4, r * 0.075)
      ..strokeCap = StrokeCap.round
      ..color = flare.withValues(alpha: 0.95);
    canvas.drawArc(Rect.fromCircle(center: c, radius: r * 0.62), flareStart,
        flareSweep, false, arc);

    // Void core ring: the aperture itself, a faint full circle.
    final ring = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..color = ink.withValues(alpha: 0.35);
    canvas.drawCircle(c, r * 0.30, ring);
  }

  @override
  bool shouldRepaint(_AperturePainter old) =>
      old.ink != ink || old.flare != flare;
}
