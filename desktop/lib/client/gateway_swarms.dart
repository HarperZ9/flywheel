// Typed subagent-swarm API: list, snapshot (which adopts detached swarms),
// spawn, and cancel. Lives beside GatewayClient rather than inside it, so
// the grandfathered core client file does not grow.
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'gateway_auth.dart';
import 'gateway_error.dart';

class SwarmsApi {
  final String baseUrl;
  final http.Client _http;

  SwarmsApi({String? baseUrl, http.Client? httpClient})
      : baseUrl = baseUrl ?? 'http://127.0.0.1:8799',
        _http = httpClient ?? AuthedClient(http.Client());

  Map<String, dynamic> _decode(http.Response r) {
    final text = utf8.decode(r.bodyBytes);
    if (r.statusCode >= 400) {
      throw GatewayException.fromResponse(r.statusCode, text);
    }
    final body = jsonDecode(text);
    return body is Map<String, dynamic> ? body : <String, dynamic>{};
  }

  /// GET /api/subagents -- live, sealed, and detached swarm rows.
  Future<Map<String, dynamic>> list() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/subagents'));
    return _decode(r);
  }

  /// GET /api/subagents/swarm?id=ID -- live snapshot or sealed receipt.
  /// Asking for a detached swarm adopts it engine-side.
  Future<Map<String, dynamic>> snapshot(String swarmId) async {
    final r = await _http
        .get(Uri.parse('$baseUrl/api/subagents/swarm?id=$swarmId'));
    return _decode(r);
  }

  /// POST /api/subagents/spawn -- fan out role-prompted children.
  Future<Map<String, dynamic>> spawn({
    required String goal,
    required String endpoint,
    required List<Map<String, String>> children,
    String quorumPolicy = 'majority',
    int maxSteps = 6,
  }) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/subagents/spawn'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'goal': goal,
        'endpoint': endpoint,
        'children': children,
        'quorum_policy': quorumPolicy,
        'max_steps': maxSteps,
      }),
    );
    return _decode(r);
  }

  /// POST /api/subagents/cancel -- stop handles or kill recorded pids,
  /// then seal what actually finished.
  Future<Map<String, dynamic>> cancel(String swarmId) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/subagents/cancel'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'swarm_id': swarmId}),
    );
    return _decode(r);
  }
}
