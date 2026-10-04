// lane_state.dart - reading the engine's lane state for the Tools view.
//
// The engine owns every state (harness/lane_roster_row.py). This file only
// names them for the card, counts them for the headline, and keeps a probed
// row on screen until a newer probe replaces it (D1). A lane the build holds
// back (code `lane_held`) is counted apart from a launch defect, and so is an
// adapter lane (code `lane_adapter_only`): it has no MCP server for the app to
// start, by design, and the engine's adapter runs its program per call.

import 'lane_models.dart';

/// The engine's states, in the order the view lists them.
const laneStates = [
  'ready',
  'limited',
  'reads_only',
  'needs_setup',
  'not_checked',
  'unreachable',
  'cannot_launch',
];

/// The count keys: the states plus a held lane, which is not a defect.
const laneCountKeys = [...laneStates, 'not_in_build'];

bool isLaneHeld(Lane lane) =>
    lane.state == 'cannot_launch' &&
    (lane.code == 'lane_held' || lane.code == 'lane_adapter_only');

/// The count key for [lane]; empty when the engine reported no state.
String laneCountKey(Lane lane) {
  if (isLaneHeld(lane)) return 'not_in_build';
  return laneStates.contains(lane.state) ? lane.state : '';
}

/// The pill text on the card.
String laneStateLabel(Lane lane) => switch (laneCountKey(lane)) {
      'ready' => 'ready',
      'limited' => 'limited',
      'reads_only' => 'reads only',
      'needs_setup' => 'needs setup',
      'not_checked' => 'not checked',
      'unreachable' => 'unreachable',
      'cannot_launch' => 'cannot start',
      'not_in_build' => 'not in build',
      _ => 'unknown',
    };

/// The verdict color key: a running main tool is verified, a step or a
/// defect is drift, and anything unchecked or held back is unverifiable.
String laneCountVerdict(String key) => switch (key) {
      'ready' || 'limited' || 'reads_only' => 'verified',
      'needs_setup' || 'unreachable' || 'cannot_launch' => 'drift',
      _ => 'unverifiable',
    };

/// The card's first line. The engine writes it; these are the fallbacks
/// for a row that arrives without one.
String laneSentence(Lane lane) {
  if (lane.sentence.isNotEmpty) return lane.sentence;
  return switch (laneCountKey(lane)) {
    'not_checked' => 'Not checked yet.',
    'not_in_build' => 'Not in this build.',
    'cannot_launch' => 'Could not start: ${lane.code.isEmpty ? 'unknown' : lane.code}.',
    '' => 'This engine does not report what the lane can run.',
    _ => '',
  };
}

/// "Checked <time>." for a probe in this engine session, "Last checked
/// <time>." for one kept from an earlier session, empty when never checked.
String laneCheckedLine(Lane lane) {
  final at = lane.lastChecked;
  if (at == null) return '';
  final when = _localTime(at);
  return lane.checkedThisSession ? 'Checked $when.' : 'Last checked $when.';
}

String _localTime(String iso) {
  final parsed = DateTime.tryParse(iso);
  if (parsed == null) return iso;
  final t = parsed.toLocal();
  String two(int n) => n.toString().padLeft(2, '0');
  return '${t.year}-${two(t.month)}-${two(t.day)} ${two(t.hour)}:${two(t.minute)}';
}

/// Sort rank: the state order, then lanes the engine gave no state.
int laneStateRank(Lane lane) {
  final key = laneCountKey(lane);
  final i = laneCountKeys.indexOf(key);
  return i < 0 ? laneCountKeys.length : i;
}

/// Whether every row in [roster] carries a state the view knows.
bool rosterReportsState(LaneRoster roster) =>
    roster.lanes.isNotEmpty &&
    roster.lanes.every((lane) => laneCountKey(lane).isNotEmpty);

/// Counts per key, from the rows themselves (D2, D9).
Map<String, int> laneStateCounts(Iterable<Lane> lanes) {
  final counts = <String, int>{};
  for (final lane in lanes) {
    final key = laneCountKey(lane);
    if (key.isNotEmpty) counts[key] = (counts[key] ?? 0) + 1;
  }
  return {
    for (final key in laneCountKeys)
      if (counts.containsKey(key)) key: counts[key]!
  };
}

/// [next] with each lane's kept probe answer preserved until a newer probe
/// replaces it (D1). A read that no longer holds the probe (an engine
/// restarted without its cache) keeps the kept row as "Last checked".
LaneRoster mergeLaneRoster(LaneRoster? previous, LaneRoster next) {
  if (previous == null) return next;
  final kept = {for (final lane in previous.lanes) lane.name: lane};
  final rows = [
    for (final lane in next.lanes) _mergeRow(kept[lane.name], lane)
  ];
  return next.withLanes(rows, probed: next.probed || previous.probed);
}

Lane _mergeRow(Lane? kept, Lane next) {
  final keptAt = kept?.lastChecked;
  if (kept == null || keptAt == null) return next;
  final nextAt = next.lastChecked;
  if (nextAt == null) return kept.asEarlierSession();
  final order = _compareTimes(nextAt, keptAt);
  if (order < 0) return kept;
  if (order == 0) return next.withProbeFactsFrom(kept);
  return next;
}

int _compareTimes(String a, String b) {
  final x = DateTime.tryParse(a);
  final y = DateTime.tryParse(b);
  return (x != null && y != null) ? x.compareTo(y) : a.compareTo(b);
}

/// [roster] with [row] in place of the lane of the same name, or appended.
LaneRoster replaceLaneRow(LaneRoster roster, Lane row) {
  final rows = [...roster.lanes];
  final i = rows.indexWhere((lane) => lane.name == row.name);
  if (i < 0) {
    rows.add(row);
  } else {
    rows[i] = row;
  }
  return roster.withLanes(rows);
}
