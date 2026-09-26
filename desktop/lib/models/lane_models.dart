// lane_models.dart - the lane roster models (GET /api/lanes).
//
// Split out of gateway_models.dart so that file stays under the 300-line
// gate; gateway_models.dart re-exports this file, so existing imports keep
// working. Parsing is defensive: missing fields degrade to defaults.

/// A single lane in the lane roster (GET /api/lanes).
class Lane {
  final String name;
  final String kind;
  final String? installedVersion;
  final String expectedVersion;
  final String status; // live | declared | missing | stale
  final String organ;
  final String role;
  final String detail;
  final int? tools; // MCP tool count, present only after a real probe
  final bool packageInstallable;

  Lane({
    required this.name,
    required this.kind,
    this.installedVersion,
    required this.expectedVersion,
    required this.status,
    required this.organ,
    required this.role,
    required this.detail,
    this.tools,
    this.packageInstallable = true,
  });

  factory Lane.fromJson(Map<String, dynamic> j) => Lane(
        name: j['name'] ?? '',
        kind: j['kind'] ?? '',
        installedVersion: j['installed_version'],
        expectedVersion: j['expected_version'] ?? '',
        status: j['status'] ?? 'missing',
        organ: j['organ'] ?? '',
        role: j['role'] ?? '',
        detail: j['detail'] ?? '',
        tools: j['tools'] is int ? j['tools'] : null,
        packageInstallable: j['package_installable'] != false,
      );

  bool get isLive => status == 'live';
  bool get isDeclared => status == 'declared';
  bool get isMissing => status == 'missing';

  /// Whether there is an install for this lane to run. A bundled lane ships
  /// inside the engine and a remote lane runs on somebody else's host, so
  /// `install_lane` answers "no install needed" for both. Offering the button
  /// there promises work the gateway will not do.
  bool get isInstallable =>
      packageInstallable && (kind == 'pip' || kind == 'npm');
}

/// The full lane roster (GET /api/lanes).
class LaneRoster {
  final int nLanes;
  final Map<String, int> byStatus;
  final bool allLive;
  final List<Lane> lanes;

  LaneRoster({
    required this.nLanes,
    required this.byStatus,
    required this.allLive,
    required this.lanes,
  });

  factory LaneRoster.fromJson(Map<String, dynamic> j) => LaneRoster(
        nLanes: j['n_lanes'] ?? 0,
        byStatus: Map<String, int>.from(j['by_status'] ?? {}),
        allLive: j['all_live'] ?? false,
        lanes: ((j['lanes'] ?? []) as List)
            .map((e) => Lane.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}
