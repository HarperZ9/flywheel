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

  const CallableLane({
    required this.name,
    this.minTier = '',
    this.description = '',
    this.organ = '',
  });

  factory CallableLane.fromJson(Map<String, dynamic> json) => CallableLane(
        name: '${json['name'] ?? ''}',
        minTier: '${json['min_tier'] ?? ''}',
        description: '${json['description'] ?? ''}',
        organ: '${json['organ'] ?? ''}',
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
