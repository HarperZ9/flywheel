// The diff surface renders raw, unreviewed, unaccepted text. Color means a
// verdict only, so added/removed lines must be distinguished by the +/- glyph
// and the ink ramp, never painted in the verified/drift verdict palette (which
// everywhere else asserts the engine accepted or flagged the work).
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/ide/diff.dart';
import 'package:flywheel_desktop/ide/diff_view.dart';
import 'package:flywheel_desktop/theme/tokens.dart';

void main() {
  const t = FwTokens.light;

  test('no diff kind uses the verdict colors', () {
    for (final k in DiffKind.values) {
      final s = diffLineStyle(t, k);
      expect(s.color, isNot(t.verified), reason: '$k must not use verified');
      expect(s.color, isNot(t.drift), reason: '$k must not use drift');
      expect(s.background, isNot(t.verified), reason: '$k bg not verified');
      expect(s.background, isNot(t.drift), reason: '$k bg not drift');
    }
  });

  test('add and del are distinguished by the glyph, from the ink ramp', () {
    final add = diffLineStyle(t, DiffKind.add);
    final del = diffLineStyle(t, DiffKind.del);
    expect(add.marker, '+');
    expect(del.marker, '−');
    // added is present (ink), removed recedes (fainter ink): distinguishable
    // without any verdict color
    expect(add.color, isNot(del.color));
  });

  test('the +/- counts also avoid the verdict palette', () {
    expect(diffCountColor(t, added: true), isNot(t.verified));
    expect(diffCountColor(t, added: false), isNot(t.drift));
  });
}
