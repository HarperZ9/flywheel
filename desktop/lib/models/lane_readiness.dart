/// Presence counts are distinct from successful MCP probes.
String laneReadinessDetail(Object? total, Map<String, dynamic> counts,
    {bool unknown = false, bool probeRequested = false}) {
  final values = [
    for (final key in ['live', 'declared', 'missing', 'stale'])
      counts.containsKey(key) ? counts[key] : 0
  ];
  if (unknown ||
      counts.keys
          .any((k) => !['live', 'declared', 'missing', 'stale'].contains(k)) ||
      total is! int ||
      total < 0 ||
      values.any((v) => v is! int || v < 0) ||
      values.fold<int>(0, (sum, v) => sum + (v as int)) != total) {
    return 'engine online · lane readiness unknown';
  }
  if (total == 0) return 'engine online · no lanes declared';
  final [live, declared, missing, stale] = values;
  if (live == total) return '$live/$total lanes live';
  return [
    if (live > 0) '$live live',
    if (declared > 0) '$declared ${probeRequested ? 'unverified' : 'not probed'}',
    if (missing > 0) '$missing missing',
    if (stale > 0) '$stale stale',
  ].join(' · ');
}
