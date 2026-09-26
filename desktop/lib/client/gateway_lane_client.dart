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
}
