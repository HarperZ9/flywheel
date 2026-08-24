// system_text_scaler.dart -- composed text scaling.
//
// The operating system's accessibility scaling and the user's in-app
// scale must MULTIPLY, never replace each other: a low-vision user who
// sets 200 percent system-wide must not lose that setting because the
// app also offers its own zoom.
import 'package:flutter/painting.dart';

class ComposedTextScaler extends TextScaler {
  final TextScaler system;
  final double userScale;

  const ComposedTextScaler({required this.system, this.userScale = 1.0});

  @override
  double get textScaleFactor => system.scale(1.0) * userScale;

  @override
  double scale(double fontSize) => system.scale(fontSize) * userScale;
}
