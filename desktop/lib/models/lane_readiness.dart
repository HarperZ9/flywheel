import 'lane_models.dart';
import 'lane_state.dart';

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

/// The Tools headline. It counts each row's state (D2, D9). An engine that
/// reports no state keeps the presence wording, and says "unverified" only
/// after this app asked it to probe.
String laneRosterDetail(LaneRoster roster) {
  if (!rosterReportsState(roster)) {
    return laneReadinessDetail(roster.nLanes, roster.byStatus,
        probeRequested: roster.probed);
  }
  final counts = laneStateCounts(roster.lanes);
  final total = roster.lanes.length;
  if (counts['ready'] == total) return '$total of $total lanes ready';
  return [
    for (final entry in counts.entries)
      '${entry.value} ${laneCountPhrase(entry.key, entry.value)}'
  ].join(' · ');
}

/// The headline words after a count.
String laneCountPhrase(String key, int count) => switch (key) {
      'ready' => 'ready',
      'limited' => 'limited',
      'reads_only' => 'reads only',
      'needs_setup' => count == 1 ? 'needs setup' : 'need setup',
      'not_checked' => 'not checked',
      'unreachable' => 'unreachable',
      'cannot_launch' => 'cannot start',
      'not_in_build' => 'not in this build',
      _ => key,
    };
