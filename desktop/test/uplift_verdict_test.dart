// Legacy retry comparisons remain diagnostic for either sign of their delta.
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/uplift_models.dart';

UpliftDelta _d(double uplift, double lo, double hi, bool includesZero) =>
    UpliftDelta(
      provider: 'p',
      uplift: uplift,
      lo: lo,
      hi: hi,
      includesZero: includesZero,
      latencyOverheadMs: 0,
      note: '',
    );

void main() {
  test('separated legacy interval above zero is not verified uplift', () {
    final d = _d(0.18, 0.05, 0.30, false);
    expect(d.verdict, 'unverifiable');
    expect(d.isRegression, isFalse);
  });

  test('separated legacy interval below zero remains diagnostic', () {
    final d = _d(-0.12, -0.24, -0.02, false);
    expect(d.verdict, 'unverifiable');
    expect(d.isRegression, isFalse);
    expect(d.verdict, isNot('verified'));
  });

  test('interval containing zero is unverifiable', () {
    final d = _d(0.03, -0.05, 0.11, true);
    expect(d.verdict, 'unverifiable');
    expect(d.isRegression, isFalse);
  });

  test('defensive parse keeps the sign mapping', () {
    final d = UpliftDelta.fromJson({
      'provider': 'x',
      'uplift': -0.1,
      'newcombe_95': [-0.2, -0.01],
      'includes_zero': false,
    });
    expect(d.verdict, 'unverifiable');
  });
}
