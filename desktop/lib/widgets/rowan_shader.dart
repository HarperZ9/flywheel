import 'dart:ui' as ui;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

class RowanShader {
  static const assetPath = 'shaders/rowan.frag';
  static Future<ui.FragmentProgram>? _program;

  static Future<ui.FragmentProgram> load() => _program ??=
          ui.FragmentProgram.fromAsset(assetPath).catchError((Object error) {
        _program = null;
        throw error;
      });
}

class RowanPose {
  const RowanPose(
      {this.attention = Offset.zero, this.yaw = 0, this.opening = 0});
  final Offset attention;
  final double yaw;
  final double opening;

  List<double> get uniforms => [
        _finite(attention.dx, -1, 1),
        _finite(attention.dy, -1, 1),
        _finite(yaw, -0.6, 0.6),
        _finite(opening, 0, 1),
      ];

  static double _finite(double value, double min, double max) =>
      value.isFinite ? value.clamp(min, max) : 0;
}

class RowanShaderPainter extends CustomPainter {
  RowanShaderPainter(
      {required this.shader,
      required this.time,
      this.motion = false,
      this.pose = const RowanPose()})
      : super(repaint: time);
  final ui.FragmentShader shader;
  final ValueListenable<double> time;
  final bool motion;
  final RowanPose pose;

  @override
  void paint(Canvas canvas, Size size) {
    shader.setFloat(0, size.width);
    shader.setFloat(1, size.height);
    shader.setFloat(2, time.value.isFinite ? time.value : 0);
    shader.setFloat(3, motion ? 1 : 0);
    final values = pose.uniforms;
    for (var i = 0; i < values.length; i++) {
      shader.setFloat(i + 4, values[i]);
    }
    canvas.drawRect(Offset.zero & size, Paint()..shader = shader);
  }

  @override
  bool shouldRepaint(RowanShaderPainter old) =>
      old.shader != shader ||
      old.time != time ||
      old.motion != motion ||
      old.pose != pose;
}

/// A simple vector symbol when the modeled renderer cannot be used.
class RowanFallbackPainter extends CustomPainter {
  const RowanFallbackPainter(this.ink);
  final Color ink;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.shortestSide * .34;
    final stroke = Paint()
      ..color = ink
      ..style = PaintingStyle.stroke
      ..strokeWidth = size.shortestSide * .025;
    canvas.save();
    canvas.translate(center.dx, center.dy);
    canvas.rotate(-.13);
    final aperture = Rect.fromCenter(
        center: Offset.zero, width: radius * 1.7, height: radius * 2);
    canvas.drawOval(aperture, stroke);
    canvas.drawOval(aperture.deflate(size.shortestSide * .06),
        stroke..color = ink.withValues(alpha: .45));
    canvas.restore();
    canvas.drawCircle(
        center,
        radius * .62,
        Paint()
          ..shader = ui.Gradient.radial(center, radius * .62,
              [ink.withValues(alpha: .55), ink.withValues(alpha: 0)]));
  }

  @override
  bool shouldRepaint(RowanFallbackPainter old) => old.ink != ink;
}
