// display_preferences.dart -- the operating system's assistive display
// settings, read from MediaQuery in one place: text scaling, high
// contrast, reduced motion. Widgets consult these instead of guessing.
import 'package:flutter/material.dart';

class DisplayPreferences {
  final TextScaler textScaler;
  final bool highContrast;
  final bool reducedMotion;

  const DisplayPreferences({
    required this.textScaler,
    required this.highContrast,
    required this.reducedMotion,
  });

  factory DisplayPreferences.fromMediaQuery(BuildContext context) =>
      DisplayPreferences(
        textScaler: MediaQuery.textScalerOf(context),
        highContrast: MediaQuery.highContrastOf(context),
        reducedMotion: MediaQuery.disableAnimationsOf(context),
      );
}
