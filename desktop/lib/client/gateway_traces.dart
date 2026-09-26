// gateway_traces.dart - trace custody: owner presence for custody operations.
//
// When the owner picks the desktop dialog as the presence method, deleting,
// exporting or changing capture settings waits for a confirmation the app
// gives. These calls list the confirmations waiting and approve one by ref.
// Any process holding the gateway token can make the same call, so the dialog
// reduces exposure to an agent and does not block one; the gateway records
// the method with every operation.

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

  /// POST /api/traces/presence/approve - approve one waiting confirmation.
  Future<bool> approvePresence(String ref) async {
    final doc = await postJson('/api/traces/presence/approve', {'ref': ref});
    return doc['ok'] == true;
  }
}
