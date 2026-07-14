// uplift_models.dart — typed reading of the uplift bench summary
// (flywheel.uplift-summary/v1). Intervals arrive computed; includes_zero
// is the engine's honest null and renders as the unverifiable verdict —
// the client never upgrades a null into a win.

class UpliftRow {
  final String provider;
  final String arm; // bare | wrapped
  final int passes;
  final int graded;
  final int unverifiable;
  final double passRate;
  final double wilsonLo;
  final double wilsonHi;
  final double latencyMsMean;
  final double candidatesMean;

  const UpliftRow(
      {required this.provider,
      required this.arm,
      required this.passes,
      required this.graded,
      required this.unverifiable,
      required this.passRate,
      required this.wilsonLo,
      required this.wilsonHi,
      required this.latencyMsMean,
      required this.candidatesMean});

  factory UpliftRow.fromJson(Map<String, dynamic> j) {
    final w = (j['wilson_95'] is List) ? j['wilson_95'] as List : const [];
    double n(dynamic v) => v is num ? v.toDouble() : 0.0;
    int i(dynamic v) => v is num ? v.toInt() : 0;
    return UpliftRow(
      provider: j['provider'] ?? '',
      arm: j['arm'] ?? '',
      passes: i(j['passes']),
      graded: i(j['graded']),
      unverifiable: i(j['unverifiable']),
      passRate: n(j['pass_rate']),
      wilsonLo: w.isNotEmpty ? n(w[0]) : 0.0,
      wilsonHi: w.length > 1 ? n(w[1]) : 0.0,
      latencyMsMean: n(j['latency_ms_mean']),
      candidatesMean: n(j['candidates_mean']),
    );
  }
}

class UpliftDelta {
  final String provider;
  final double uplift;
  final double lo;
  final double hi;
  final bool includesZero;
  final double latencyOverheadMs;
  final String note;

  const UpliftDelta(
      {required this.provider,
      required this.uplift,
      required this.lo,
      required this.hi,
      required this.includesZero,
      required this.latencyOverheadMs,
      required this.note});

  /// The honest mapping: a separated interval is verified, an interval
  /// containing zero is unverifiable. Never drift — no uplift is a
  /// result, not a fault.
  String get verdict => includesZero ? 'unverifiable' : 'verified';

  factory UpliftDelta.fromJson(Map<String, dynamic> j) {
    final w = (j['newcombe_95'] is List) ? j['newcombe_95'] as List : const [];
    double n(dynamic v) => v is num ? v.toDouble() : 0.0;
    return UpliftDelta(
      provider: j['provider'] ?? '',
      uplift: n(j['uplift']),
      lo: w.isNotEmpty ? n(w[0]) : 0.0,
      hi: w.length > 1 ? n(w[1]) : 0.0,
      includesZero: j['includes_zero'] ?? true,
      latencyOverheadMs: n(j['latency_overhead_ms']),
      note: j['note'] ?? '',
    );
  }
}

class UpliftRun {
  final String comparisonKey;
  final int nCandidates;
  final List<UpliftRow> rows;
  final List<UpliftDelta> deltas;

  const UpliftRun(
      {required this.comparisonKey,
      required this.nCandidates,
      required this.rows,
      required this.deltas});

  factory UpliftRun.fromJson(Map<String, dynamic> j) => UpliftRun(
        comparisonKey: j['comparison_key'] ?? '',
        nCandidates: j['n_candidates'] is num
            ? (j['n_candidates'] as num).toInt()
            : 0,
        rows: ((j['rows'] ?? []) as List)
            .whereType<Map<String, dynamic>>()
            .map(UpliftRow.fromJson)
            .toList(),
        deltas: ((j['deltas'] ?? []) as List)
            .whereType<Map<String, dynamic>>()
            .map(UpliftDelta.fromJson)
            .toList(),
      );
}

class UpliftSummary {
  final List<Map<String, dynamic>> runs;
  final UpliftRun? latest;
  final String note;

  const UpliftSummary(
      {required this.runs, this.latest, required this.note});

  factory UpliftSummary.fromJson(Map<String, dynamic> j) => UpliftSummary(
        runs: ((j['runs'] ?? []) as List)
            .whereType<Map<String, dynamic>>()
            .toList(),
        latest: j['latest'] is Map<String, dynamic>
            ? UpliftRun.fromJson(j['latest'] as Map<String, dynamic>)
            : null,
        note: j['note'] ?? '',
      );
}
