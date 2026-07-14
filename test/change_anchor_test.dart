// Anchored change requests (landscape import 10): the anchor covers exactly
// the changed lines, so a request stays bound to the change it was written
// against, and a shifted diff visibly breaks the binding.
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/ide/diff.dart';

void main() {
  test('the anchor is deterministic over the changed lines', () {
    final d = diffFiles('a.py', 'x = 1\n', 'x = 2\n');
    expect(changeAnchor(d), changeAnchor(d));
    expect(changeAnchor(d).length, 16);
  });

  test('a different change moves the anchor', () {
    final a = diffFiles('a.py', 'x = 1\n', 'x = 2\n');
    final b = diffFiles('a.py', 'x = 1\n', 'x = 3\n');
    expect(changeAnchor(a), isNot(changeAnchor(b)));
  });

  test('context lines never affect the anchor', () {
    final a = diffFiles('a.py', 'k = 0\nx = 1\n', 'k = 0\nx = 2\n');
    final b = diffFiles('a.py', 'j = 9\nx = 1\n', 'j = 9\nx = 2\n');
    expect(changeAnchor(a), changeAnchor(b));
  });
}
