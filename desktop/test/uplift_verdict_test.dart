// The uplift verdict must key on the SIGN of a separated interval, not
// only on whether it straddles zero: a measured regression is drift, never
// a green verified win, and an interval containing zero stays unverifiable.
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
  test('separated interval above zero is a verified uplift', () {
    final d = _d(0.18, 0.05, 0.30, false);
    expect(d.verdict, 'verified');
    expect(d.isRegression, isFalse);
  });

  test('separated interval below zero is drift, never verified', () {
    final d = _d(-0.12, -0.24, -0.02, false);
    expect(d.verdict, 'drift');
    expect(d.isRegression, isTrue);
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
    expect(d.verdict, 'drift');
  });
}
