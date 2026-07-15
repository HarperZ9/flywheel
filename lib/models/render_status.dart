// render_status.dart — pure verdict-status decisions the views render as color.
//
// Color is a verdict only, and a verdict is the engine's, never the client's
// guess. These functions map an engine field (a verdict string, a count, a
// point estimate) onto the three-color palette honestly: absence and unknown
// are the honest null (unverifiable), a count of zero is not a green win, and
// a point estimate with no interval is never a verified claim. Each is pure so
// a stranger (and a test) can re-run the decision.

/// A count tile is verified only when the count is positive: a zero, or an
/// absent field parsed to zero, is the honest null, not a green success.
String countStatus(int count) => count > 0 ? 'verified' : 'unverifiable';

/// An envelope verdict: PASS is accepted, FAIL is drift, and UNREADABLE / '?'
/// / empty / anything else is the honest null, never a fabricated drift.
String envelopeStatus(String verdict) => switch (verdict) {
      'PASS' => 'verified',
      'FAIL' => 'drift',
      _ => 'unverifiable',
    };

/// The companion answer's status comes from the ENGINE's verdict field, not
/// the transport source label: a cache hit or a local run is not itself an
/// acceptance. PASS/MATCH is verified, DRIFT/FAIL is drift, a missing or
/// unknown verdict is the honest null.
String companionStatus(String? verdict) => switch (verdict) {
      'PASS' || 'MATCH' => 'verified',
      'DRIFT' || 'FAIL' => 'drift',
      _ => 'unverifiable',
    };

/// A harness-lift point estimate is not a verified claim without an interval
/// that separates from zero (no claim without its interval). `includesZero`
/// null means no interval was emitted, so the lift stays the honest null.
/// With a separated interval: a positive lift is verified, a negative one is
/// a measured regression (drift).
String liftStatus(double lift, {bool? includesZero}) {
  if (includesZero == null || includesZero) return 'unverifiable';
  return lift > 0 ? 'verified' : 'drift';
}
