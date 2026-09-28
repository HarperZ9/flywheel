// gateway_traces.dart - trace custody: owner presence for custody operations.
//
// A presence challenge is answered by the method in effect (Windows Hello or
// none) inside the gateway, never by an approval call: a route any process
// holding the gateway token could call would approve for an agent too. This
// call lists the challenges waiting for that answer, so the app can say that
// a prompt is open.

import 'gateway_client.dart';

extension GatewayTraces on GatewayClient {
  /// GET /api/traces/presence/pending - confirmations waiting, each with its
  /// ref, operation kind, plan digest and expiry. No summary text and no path.
  Future<List<Map<String, dynamic>>> presencePending() async {
    final doc = await getJson('/api/traces/presence/pending');
    final rows = doc['pending'];
    if (rows is! List) return const [];
    return [
      for (final row in rows)
        if (row is Map<String, dynamic>) row,
    ];
  }
}
