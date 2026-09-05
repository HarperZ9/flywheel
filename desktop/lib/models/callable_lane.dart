// callable_lane.dart - which lanes can be called, and what each demands.
//
// The lane roster says what is installed. This says what may be invoked and
// the governance tier it costs, which is a different question: a lane can be
// present and still refuse to run for an operator who has not cleared its
// tier. Nothing here is recomputed; the engine decides and this renders.

class CallableLane {
  final String name;

  /// The governance tier the caller must hold. Rendered as returned, never
  /// compared or ranked here: tier ordering is the engine's to define.
  final String minTier;
  final String description;

  /// Which organ of the workspace this lane belongs to (perception,
  /// verification, structure, orchestration, and so on).
  final String organ;

  /// The tier a tool on this lane costs when it is not in the lane's open set.
  /// Empty when every tool on the lane costs [minTier]. bulletin is the live
  /// case: reading the board is open, writing to it publishes under a
  /// persistent identity, and the engine charges those differently.
  final String unlistedToolTier;

  const CallableLane({
    required this.name,
    this.minTier = '',
    this.description = '',
    this.organ = '',
    this.unlistedToolTier = '',
  });

  /// What the tier column prints. A lane whose tools do not share one tier
  /// prints both: printing the floor alone tells an operator the whole lane is
  /// open at that tier when its write tools are not. The two are joined, never
  /// ranked, because tier ordering is the engine's to define.
  String get tierLabel =>
      unlistedToolTier.isEmpty || unlistedToolTier == minTier
          ? minTier
          : '$minTier/$unlistedToolTier';

  factory CallableLane.fromJson(Map<String, dynamic> json) => CallableLane(
        name: '${json['name'] ?? ''}',
        minTier: '${json['min_tier'] ?? ''}',
        description: '${json['description'] ?? ''}',
        organ: '${json['organ'] ?? ''}',
        unlistedToolTier: '${json['unlisted_tool_tier'] ?? ''}',
      );

  /// The list, with malformed rows dropped rather than faked. A lane the
  /// engine did not name is not a lane.
  static List<CallableLane> listFrom(Map<String, dynamic> json) {
    final raw = json['lanes'];
    if (raw is! List) return const [];
    final out = <CallableLane>[];
    for (final row in raw) {
      if (row is! Map<String, dynamic>) continue;
      final lane = CallableLane.fromJson(row);
      if (lane.name.isNotEmpty) out.add(lane);
    }
    return out;
  }
}
