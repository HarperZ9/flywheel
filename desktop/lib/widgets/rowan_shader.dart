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
  const RowanPose({this.gaze = Offset.zero, this.yaw = 0, this.mouth = 0});
  final Offset gaze;
  final double yaw;
  final double mouth;

  List<double> get uniforms => [
        _finite(gaze.dx, -1, 1),
        _finite(gaze.dy, -1, 1),
        _finite(yaw, -0.6, 0.6),
        _finite(mouth, 0, 1),
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
    final stroke = Paint()
      ..color = ink
      ..style = PaintingStyle.stroke
      ..strokeWidth = size.shortestSide * 0.04;
    canvas.drawOval(
        Rect.fromLTWH(size.width * .3, size.height * .12, size.width * .4,
            size.height * .5),
        stroke);
    final shoulders = Path()
      ..moveTo(size.width * .12, size.height * .9)
      ..quadraticBezierTo(size.width * .5, size.height * .45, size.width * .88,
          size.height * .9);
    canvas.drawPath(shoulders, stroke);
  }

  @override
  bool shouldRepaint(RowanFallbackPainter old) => old.ink != ink;
}
