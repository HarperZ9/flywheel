// tokens.dart — the Flywheel design tokens, mirrored from the engine's own
// shell (local-model site/index.html) and the ecosystem design canon
// (telos-v2 DESIGN-VOICE-CANON.md).
//
// Rules the tokens encode:
//   - Color only ever means a verdict: verified / drift / unverifiable + ink.
//   - One hot mark (drift) per view. No decorative color, no gradients.
//   - Cards are ground tints with a 1px hairline. Never glass, never shadow.
//   - Two typefaces: Hanken Grotesk (text, hierarchy from weight) and
//     Conso (mono: labels, hashes, numerals).

import 'package:flutter/material.dart';

/// The full token set for one brightness. Registered as a ThemeExtension so
/// every widget reads tokens from context, never from hardcoded constants.
class FwTokens extends ThemeExtension<FwTokens> {
  // Ground
  final Color ground; // page background
  final Color ground2; // recessed background
  final Color panel; // card tint over ground

  // Ink ramp
  final Color ink;
  final Color inkSoft;
  final Color inkMuted;
  final Color inkFaint;

  // Verdicts (the only meaningful colors)
  final Color verified;
  final Color drift;
  final Color driftSoft;
  final Color unverifiable;

  // Hairlines
  final Color line; // 1px borders
  final Color hairline; // even fainter separators

  // Typefaces. The canon pair is the default; the user may choose their
  // own. Whatever the taste, color still only ever means a verdict.
  final String textFamily;
  final String monoFamily;

  const FwTokens({
    required this.ground,
    required this.ground2,
    required this.panel,
    required this.ink,
    required this.inkSoft,
    required this.inkMuted,
    required this.inkFaint,
    required this.verified,
    required this.drift,
    required this.driftSoft,
    required this.unverifiable,
    required this.line,
    required this.hairline,
    this.textFamily = 'Hanken Grotesk',
    this.monoFamily = 'Conso',
  });

  /// Ceramic light — the canon default.
  static const light = FwTokens(
    ground: Color(0xFFF4F3EF),
    ground2: Color(0xFFECEAE4),
    panel: Color(0x9EFFFFFF), // white 62%
    ink: Color(0xFF0B0C0E),
    inkSoft: Color(0xFF24272C),
    inkMuted: Color(0xFF43474E),
    inkFaint: Color(0xFF6C707A),
    verified: Color(0xFF1F7A52),
    drift: Color(0xFF3A2BD6),
    driftSoft: Color(0xFF5A4CE0),
    unverifiable: Color(0xFF6C707A),
    line: Color(0x240B0C0E), // ink 14%
    hairline: Color(0x140B0C0E), // ink 8%
  );

  /// Near-black dark — mirrors the shell's dark theme exactly.
  static const dark = FwTokens(
    ground: Color(0xFF0B0E0F),
    ground2: Color(0xFF121617),
    panel: Color(0x0BFFFFFF), // white 4.5%
    ink: Color(0xFFEEF1EE),
    inkSoft: Color(0xFFCFD5D1),
    inkMuted: Color(0xFF9AA39C),
    inkFaint: Color(0xFF7B857E),
    verified: Color(0xFF5FAE93),
    drift: Color(0xFFA99CF5),
    driftSoft: Color(0xFFC3BCF7),
    unverifiable: Color(0xFF9AA39C),
    line: Color(0x29EEF1EE), // ink 16%
    hairline: Color(0x1AEEF1EE), // ink 10%
  );

  /// Verdict color for a lane / receipt / endpoint status string.
  /// live+verified = accept path; declared/absent = unverifiable (present but
  /// unproven); stale/missing/error = drift (caution, honest null). No red:
  /// color is a verdict, and drift IS the caution verdict.
  Color statusColor(String status) {
    switch (status) {
      case 'live':
      case 'verified':
      case 'pass':
      case 'match':
      case 'present':
      case 'healthy':
        return verified;
      case 'declared':
      case 'unverifiable':
      case 'absent':
      case 'pending':
        return unverifiable;
      default: // stale, missing, drift, error
        return drift;
    }
  }

  @override
  FwTokens copyWith({
    Color? ground,
    Color? ground2,
    Color? panel,
    Color? ink,
    Color? inkSoft,
    Color? inkMuted,
    Color? inkFaint,
    Color? verified,
    Color? drift,
    Color? driftSoft,
    Color? unverifiable,
    Color? line,
    Color? hairline,
    String? textFamily,
    String? monoFamily,
  }) {
    return FwTokens(
      ground: ground ?? this.ground,
      ground2: ground2 ?? this.ground2,
      panel: panel ?? this.panel,
      ink: ink ?? this.ink,
      inkSoft: inkSoft ?? this.inkSoft,
      inkMuted: inkMuted ?? this.inkMuted,
      inkFaint: inkFaint ?? this.inkFaint,
      verified: verified ?? this.verified,
      drift: drift ?? this.drift,
      driftSoft: driftSoft ?? this.driftSoft,
      unverifiable: unverifiable ?? this.unverifiable,
      line: line ?? this.line,
      hairline: hairline ?? this.hairline,
      textFamily: textFamily ?? this.textFamily,
      monoFamily: monoFamily ?? this.monoFamily,
    );
  }

  @override
  FwTokens lerp(FwTokens? other, double t) {
    if (other == null) return this;
    return FwTokens(
      ground: Color.lerp(ground, other.ground, t)!,
      ground2: Color.lerp(ground2, other.ground2, t)!,
      panel: Color.lerp(panel, other.panel, t)!,
      ink: Color.lerp(ink, other.ink, t)!,
      inkSoft: Color.lerp(inkSoft, other.inkSoft, t)!,
      inkMuted: Color.lerp(inkMuted, other.inkMuted, t)!,
      inkFaint: Color.lerp(inkFaint, other.inkFaint, t)!,
      verified: Color.lerp(verified, other.verified, t)!,
      drift: Color.lerp(drift, other.drift, t)!,
      driftSoft: Color.lerp(driftSoft, other.driftSoft, t)!,
      unverifiable: Color.lerp(unverifiable, other.unverifiable, t)!,
      line: Color.lerp(line, other.line, t)!,
      hairline: Color.lerp(hairline, other.hairline, t)!,
      textFamily: t < 0.5 ? textFamily : other.textFamily,
      monoFamily: t < 0.5 ? monoFamily : other.monoFamily,
    );
  }
}

/// Shorthand: `context.fw` returns the active token set.
extension FwTokensContext on BuildContext {
  FwTokens get fw => Theme.of(this).extension<FwTokens>()!;
}

/// Layout constants shared across views. 8-based scale, canon radii, and the
/// single transition duration (150ms ease, killed under reduced motion).
class FwLayout {
  static const double s1 = 4, s2 = 8, s3 = 12, s4 = 16, s5 = 24, s6 = 32;
  static const double radius = 10;
  static const double radiusSmall = 8;
  static const Duration transition = Duration(milliseconds: 150);
}
