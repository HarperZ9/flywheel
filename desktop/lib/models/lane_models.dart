// lane_models.dart - the lane roster models (GET /api/lanes).
//
// Split out of gateway_models.dart so that file stays under the 300-line
// gate; gateway_models.dart re-exports this file, so existing imports keep
// working. Parsing is defensive: missing fields degrade to defaults.
//
// Each row carries two answers. `status` is presence (live, declared,
// missing, stale). `state` is what the lane can do, from the engine's probe
// cache, its tool policy and its setup checks (PLAN section 2). The card and
// the counts read `state`; an engine that reports none leaves it empty.

/// One setup item as the engine states it. It never carries a secret.
class LaneSetupItem {
  final String id;
  final bool met;
  final String title;
  final String copy;

  const LaneSetupItem({
    required this.id,
    required this.met,
    required this.title,
    required this.copy,
  });

  static LaneSetupItem? tryParse(Object? j) {
    if (j is! Map) return null;
    final id = j['id'];
    if (id is! String || id.isEmpty) return null;
    return LaneSetupItem(
      id: id,
      met: j['met'] == true,
      title: _text(j['title']),
      copy: _text(j['copy']),
    );
  }
}

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

  /// The engine's state; empty when the engine reports none.
  final String state;
  final String sentence;
  final String secondLine;
  final String? lastChecked;
  final bool checkedThisSession;
  final String code;
  final List<LaneSetupItem> setup;
  final String mainAction;
  final List<String> mainTools;
  final String versionLabel;

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
    this.state = '',
    this.sentence = '',
    this.secondLine = '',
    this.lastChecked,
    this.checkedThisSession = false,
    this.code = '',
    this.setup = const [],
    this.mainAction = '',
    this.mainTools = const [],
    this.versionLabel = '',
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
        state: _text(j['state']),
        sentence: _text(j['sentence']),
        secondLine: _text(j['second_line']),
        lastChecked: _nonEmpty(j['last_checked']),
        checkedThisSession: j['checked_this_session'] == true,
        code: _text(j['code']),
        setup: [
          for (final item in (j['setup'] is List ? j['setup'] as List : []))
            if (LaneSetupItem.tryParse(item) case final parsed?) parsed
        ],
        mainAction: _text(j['main_action']),
        mainTools: [
          for (final t in (j['main_tools'] is List ? j['main_tools'] as List : []))
            if (t is String) t
        ],
        versionLabel: _text(j['version_label']),
      );

  /// This row with the facts only a probe reports taken from [probed], the
  /// kept row of the same probe. `state` stays this row's: the engine
  /// recomputes it from the current setup on every read.
  Lane withProbeFactsFrom(Lane probed) => _copy(
      status: probed.status, detail: probed.detail, tools: probed.tools);

  /// This row as an answer from an earlier engine session.
  Lane asEarlierSession() => _copy(checkedThisSession: false);

  Lane _copy({String? status, String? detail, int? tools,
          bool? checkedThisSession}) =>
      Lane(
        name: name,
        kind: kind,
        installedVersion: installedVersion,
        expectedVersion: expectedVersion,
        status: status ?? this.status,
        organ: organ,
        role: role,
        detail: detail ?? this.detail,
        tools: tools ?? this.tools,
        packageInstallable: packageInstallable,
        state: state,
        sentence: sentence,
        secondLine: secondLine,
        lastChecked: lastChecked,
        checkedThisSession: checkedThisSession ?? this.checkedThisSession,
        code: code,
        setup: setup,
        mainAction: mainAction,
        mainTools: mainTools,
        versionLabel: versionLabel,
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

  /// Whether this read asked the engine to probe every lane.
  final bool probed;

  LaneRoster({
    required this.nLanes,
    required this.byStatus,
    required this.allLive,
    required this.lanes,
    this.probed = false,
  });

  factory LaneRoster.fromJson(Map<String, dynamic> j, {bool probed = false}) =>
      LaneRoster(
        nLanes: j['n_lanes'] ?? 0,
        byStatus: Map<String, int>.from(j['by_status'] ?? {}),
        allLive: j['all_live'] ?? false,
        lanes: ((j['lanes'] ?? []) as List)
            .map((e) => Lane.fromJson(e as Map<String, dynamic>))
            .toList(),
        probed: probed,
      );

  /// The same roster holding [rows] in place of its lanes.
  LaneRoster withLanes(List<Lane> rows, {bool? probed}) => LaneRoster(
        nLanes: nLanes,
        byStatus: byStatus,
        allLive: allLive,
        lanes: rows,
        probed: probed ?? this.probed,
      );
}

String _text(Object? v) => v is String ? v : '';

String? _nonEmpty(Object? v) => v is String && v.isNotEmpty ? v : null;
