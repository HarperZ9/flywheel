// The measurement contract: only a real measurement (a parsed deviation and
// a named method) rides to crucible; a blank or half-filled expander must
// never fabricate a zero-deviation "measurement" that could flip a verdict.
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/widgets/science_composer.dart';

void main() {
  test('an unmeasured claim contributes no measurement', () {
    final c = ScienceClaim()..text.text = 'the solver converges';
    expect(c.measurementJson(0), isNull);
    expect(c.claimJson(0), {
      'id': 'c1',
      'text': 'the solver converges',
      'falsification': '',
    });
    c.dispose();
  });

  test('a toggled-on but empty measurement is not fabricated', () {
    final c = ScienceClaim()
      ..text.text = 'residual < 1e-4'
      ..measured = true;
    expect(c.measurementJson(0), isNull); // no deviation, no method
    c.deviation.text = '0.00009';
    expect(c.measurementJson(0), isNull); // still no method
    c.dispose();
  });

  test('a complete measurement carries the crucible contract shape', () {
    final c = ScienceClaim()
      ..text.text = 'residual < 1e-4'
      ..measured = true;
    c.deviation.text = '0.00009';
    c.tolerance.text = '0.0001';
    c.method.text = 'gauss-seidel sweep count at omega=1.9';
    c.evidence.text = 'harness/field_studio.py receipt';
    expect(c.measurementJson(2), {
      'claim': 'c3',
      'deviation': 0.00009,
      'tolerance': 0.0001,
      'method': 'gauss-seidel sweep count at omega=1.9',
      'evidence': 'harness/field_studio.py receipt',
    });
    c.dispose();
  });

  test('an empty claim row is skipped entirely', () {
    final c = ScienceClaim();
    expect(c.claimJson(0), isNull);
    c.dispose();
  });
}
