// gateway_forum.dart - the forum lane's reads as typed client calls.

import 'gateway_client.dart';

/// The forum lane, proxied by the gateway over MCP.
///
/// Each route spawns the lane's MCP server and returns its JSON, or an
/// `{"error": ...}` when the lane is down. The lane being offline is a normal
/// state to render, not an exception to throw, so every accessor here returns
/// the map as-is and the models decide what it means.
extension GatewayForum on GatewayClient {
  /// GET /api/forum/status - the lane's own action envelope.
  Future<Map<String, dynamic>> forumStatus() => getJson('/api/forum/status');

  /// GET /api/forum/ledger - counters and the ledger checkpoint.
  Future<Map<String, dynamic>> forumLedger() => getJson('/api/forum/ledger');

  /// GET /api/forum/gates - waves paused for human approval.
  Future<Map<String, dynamic>> forumGates() => getJson('/api/forum/gates');

  /// GET /api/forum/run-room - the current run projected for an operator.
  Future<Map<String, dynamic>> forumRunRoom() =>
      getJson('/api/forum/run-room');
}
