// fw_layout.dart -- layout constants shared across views. The 8-based
// scale, canon radii, and the single transition duration (150ms ease,
// killed under reduced motion). One definition; theme/tokens.dart
// re-exports it so existing imports keep working.

class FwLayout {
  static const double s1 = 4, s2 = 8, s3 = 12, s4 = 16, s5 = 24, s6 = 32;
  static const double radius = 10;
  static const double radiusSmall = 8;
  static const Duration transition = Duration(milliseconds: 150);
}
