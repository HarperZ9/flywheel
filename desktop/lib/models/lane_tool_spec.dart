// lane_tool_spec.dart - one lane tool as the engine lists it for the console.
//
// `POST /api/lanes/<lane>/tools` (harness/lane_console_route.py) lists every
// tool the lane's server offers, marked against the engine's tool policy:
// admitted, tier, not_in_build, main, timeout_s, needs and path_args. Nothing
// here recomputes that policy. The console renders it, builds the one
// lane.call the owner approves, and reads the answer, which may be any JSON
// value or one fixed lane error code.

import 'gateway_grant_models.dart';
import 'tool_spec.dart';

const laneToolsSchema = 'flywheel.lane-tools/v1';

/// How much longer the desktop waits than the engine's own tool timeout.
const laneClientWaitExtra = Duration(seconds: 10);

/// One HTTP answer: the status and the decoded body, whatever it was.
typedef LaneAnswer = ({int status, Object? body});

class LaneToolSpec {
  final String name, description, tier, notInBuild;
  final Map<String, dynamic> inputSchema;
  final bool listed, admitted, main;
  final int timeoutS;
  final List<String> needs, pathArgs;

  const LaneToolSpec({
    required this.name,
    this.description = '',
    this.tier = 'T1',
    this.notInBuild = '',
    this.inputSchema = const {},
    this.listed = true,
    this.admitted = false,
    this.main = false,
    this.timeoutS = 20,
    this.needs = const [],
    this.pathArgs = const [],
  });

  static LaneToolSpec? tryParse(Object? raw) {
    if (raw is! Map) return null;
    final name = raw['name'];
    if (name is! String || name.isEmpty) return null;
    final timeout = raw['timeout_s'];
    return LaneToolSpec(
      name: name,
      description: _text(raw['description']),
      tier: _text(raw['tier']).isEmpty ? 'T1' : _text(raw['tier']),
      notInBuild: _text(raw['not_in_build']),
      inputSchema: raw['inputSchema'] is Map
          ? Map<String, dynamic>.from(raw['inputSchema'] as Map)
          : const {},
      listed: raw['listed'] != false,
      admitted: raw['admitted'] == true,
      main: raw['main'] == true,
      timeoutS: timeout is int && timeout > 0 ? timeout : 20,
      needs: _strings(raw['needs']),
      pathArgs: _strings(raw['path_args']),
    );
  }

  /// The schema the argument form renders.
  ToolSpec get spec =>
      ToolSpec(name: name, description: description, inputSchema: inputSchema);

  /// A tool above T1 runs only when the approval names its tier.
  bool get needsTier => tier != 'T1';

  /// Why the console cannot run this tool here, or empty when it can.
  String get blockedReason {
    if (notInBuild.isNotEmpty) return 'Not in this build ($notInBuild).';
    if (!listed) return 'The lane does not list this tool.';
    if (!needsTier && !admitted) return 'This build does not admit it.';
    return '';
  }

  bool get runnable => blockedReason.isEmpty;

  /// The engine's timeout for the tool plus the desktop's own margin.
  Duration get clientWait => Duration(seconds: timeoutS) + laneClientWaitExtra;
}

class LaneToolListing {
  final String lane;
  final List<LaneToolSpec> tools;
  const LaneToolListing(this.lane, this.tools);

  /// The listing for [lane], or null when the body is not one. Main tools
  /// come first, then the other runnable tools, then the blocked ones.
  static LaneToolListing? tryParse(Object? body, String lane) {
    if (body is! Map || body['schema'] != laneToolsSchema) return null;
    if (body['lane'] != lane || body['tools'] is! List) return null;
    final tools = [
      for (final raw in body['tools'] as List)
        if (LaneToolSpec.tryParse(raw) case final tool?) tool
    ]..sort(_order);
    return LaneToolListing(lane, tools);
  }

  List<LaneToolSpec> get runnable => [
        for (final t in tools)
          if (t.runnable) t
      ];
  List<LaneToolSpec> get blocked => [
        for (final t in tools)
          if (!t.runnable) t
      ];
}

int _order(LaneToolSpec a, LaneToolSpec b) {
  int rank(LaneToolSpec t) => !t.runnable ? 2 : (t.main ? 0 : 1);
  final byRank = rank(a).compareTo(rank(b));
  return byRank != 0 ? byRank : a.name.compareTo(b.name);
}

/// The one lane.call the owner approves for [tool] with [args]. It carries
/// the policy timeout, the tool's tier when it is above T1, and lets the
/// tool's own path arguments hold a local path.
GatewayOperation laneCallOperation(String lane, LaneToolSpec tool,
        Map<String, dynamic> args, String clientRequestId) =>
    GatewayOperation.exact(
      action: 'lane.call',
      clientRequestId: clientRequestId,
      operation: {
        'name': lane,
        'tool': tool.name,
        'args': args,
        'timeout': tool.timeoutS,
        if (tool.needsTier) 'governance_tier': tool.tier,
      },
      pathKeys: tool.pathArgs.toSet(),
    );

/// A failed lane answer: the engine's fixed code and its closed fields.
class LaneError {
  final String code, reason;
  final int status;
  final List<String> admitted, setup;
  final int? timeoutS;
  const LaneError(this.code,
      {this.reason = '',
      this.status = 0,
      this.admitted = const [],
      this.setup = const [],
      this.timeoutS});

  /// The error in [answer], or null when the answer is a result.
  static LaneError? of(LaneAnswer answer) {
    final body = answer.body;
    final coded =
        body is Map && body['code'] is String && body['error'] != null;
    if (answer.status == 200 && !coded) return null;
    if (body is! Map) return LaneError('NO_BODY', status: answer.status);
    final code = _text(body['code']);
    return LaneError(
      code.isEmpty ? _uncoded(answer.status, body) : code,
      reason: _text(body['reason']),
      status: answer.status,
      admitted: _strings(body['admitted']),
      setup: _strings(body['setup']),
      timeoutS: body['timeout_s'] is int ? body['timeout_s'] as int : null,
    );
  }
}

String _uncoded(int status, Map body) =>
    status == 403 || body['governance_denied'] != null
        ? 'GOVERNANCE_DENIED'
        : 'UNKNOWN';

String _text(Object? v) => v is String ? v : '';

List<String> _strings(Object? v) => v is List
    ? [
        for (final item in v)
          if (item is String) item
      ]
    : const [];
