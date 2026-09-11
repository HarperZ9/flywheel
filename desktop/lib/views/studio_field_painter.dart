part of 'studio_view.dart';

class _FieldPainter extends CustomPainter {
  final int seed;
  final Color ground;
  _FieldPainter({required this.seed, required this.ground});

  static const _band = [
    Color(0xFFC2447F),
    Color(0xFFC96F3A),
    Color(0xFFC9A23A),
    Color(0xFF6FA33C),
    Color(0xFF3A9FA8),
    Color(0xFF6C5CE0),
  ];

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = ground);
    final rng = Mulberry32(seed);
    final cx = size.width * (0.25 + 0.5 * rng.next());
    final cy = size.height * (0.3 + 0.4 * rng.next());
    final k1 = 1.5 + rng.next() * 2.5;
    final k2 = 0.8 + rng.next() * 1.8;
    const arcs = 130;
    for (var i = 0; i < arcs; i++) {
      var x = size.width * rng.next();
      var y = size.height * rng.next();
      final color = _band[i % _band.length];
      final paint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 0.7
        ..color = color.withValues(alpha: 0.30 + 0.30 * rng.next());
      final path = Path()..moveTo(x, y);
      for (var s = 0; s < 64; s++) {
        final dx = x - cx, dy = y - cy;
        final r = math.sqrt(dx * dx + dy * dy) + 1e-6;
        final angle = math.atan2(dy, dx) +
            math.pi / 2 +
            0.6 * math.sin(k1 * r / size.width * math.pi) +
            0.3 * math.cos(k2 * x / size.width * math.pi);
        x += math.cos(angle) * 3.2;
        y += math.sin(angle) * 3.2;
        if (x < -20 || y < -20 || x > size.width + 20 || y > size.height + 20) {
          break;
        }
        path.lineTo(x, y);
      }
      canvas.drawPath(path, paint);
    }
  }

  @override
  bool shouldRepaint(_FieldPainter old) =>
      old.seed != seed || old.ground != ground;
}
