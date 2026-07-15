// Render-status decisions: color is a verdict only, and absence / zero / an
// interval-less point estimate are the honest null, never a green win.
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/render_status.dart';

void main() {
  test('a count of zero is the honest null, positive is verified', () {
    expect(countStatus(0), 'unverifiable');
    expect(countStatus(3), 'verified');
  });

  test('envelope: PASS verified, FAIL drift, unknown honest null', () {
    expect(envelopeStatus('PASS'), 'verified');
    expect(envelopeStatus('FAIL'), 'drift');
    expect(envelopeStatus('UNREADABLE'), 'unverifiable');
    expect(envelopeStatus('?'), 'unverifiable');
    expect(envelopeStatus(''), 'unverifiable');
  });

  test('companion status comes from the engine verdict, not the source', () {
    expect(companionStatus('PASS'), 'verified');
    expect(companionStatus('MATCH'), 'verified');
    expect(companionStatus('DRIFT'), 'drift');
    expect(companionStatus(null), 'unverifiable'); // cache/local is not acceptance
    expect(companionStatus('anything'), 'unverifiable');
  });

  test('a health fraction is verified only at full health', () {
    expect(fractionStatus(3, 3), 'verified');
    expect(fractionStatus(1, 3), 'drift'); // partial health is not a green win
    expect(fractionStatus(0, 0), 'drift'); // nothing healthy, nothing to verify
  });

  test('a lift with no interval is never verified', () {
    expect(liftStatus(0.12), 'unverifiable'); // bare point estimate
    expect(liftStatus(0.005, includesZero: true), 'unverifiable'); // straddles 0
    expect(liftStatus(0.12, includesZero: false), 'verified'); // separated, positive
    expect(liftStatus(-0.08, includesZero: false), 'drift'); // separated, negative
  });
}
