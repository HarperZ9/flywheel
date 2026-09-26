part of 'gateway_client.dart';

// gateway_lane_client.dart - the lane calls on the gateway client. Split out
// of gateway_client.dart so that file stays under the 300-line gate. As a
// part of that library, importing gateway_client.dart brings these in.

extension GatewayLaneClient on GatewayClient {
  /// GET /api/lanes — the lane roster (live/declared/missing).
  Future<LaneRoster> laneRoster({bool probe = false}) async {
    final r = await _http.get(
      Uri.parse('$baseUrl/api/lanes${probe ? '?probe=true' : ''}'),
    );
    final body = _decode(r);
    if (body['n_lanes'] is! int || body['by_status'] is! Map) {
      throw const FormatException('Lane inventory was not reported');
    }
    return LaneRoster.fromJson(body);
  }

  /// GET /api/settings/node_path: the node the Node lanes use and its source.
  ///
  /// Choosing node.exe is a granted action (settings.node_path): the engine
  /// runs the file it names, so a POST needs an exact owner grant, like
  /// plugin.register. The Node picker sends it through the grant flow when
  /// the lane console lands (WP9b); there is no ungranted setter here.
  Future<Map<String, dynamic>> nodePath() async =>
      _decode(await _http.get(Uri.parse('$baseUrl/api/settings/node_path')));
}
