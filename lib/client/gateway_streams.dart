// gateway_streams.dart — the streaming and plugin surface of the client,
// as a same-library extension so it shares the private http client.

part of 'gateway_client.dart';

/// Live streams and the plugin registry. Same client, same base URL; split
/// only to keep each file within the size gate.
extension GatewayStreamsAndPlugins on GatewayClient {
  /// POST /api/agent with stream:true — the live agent event stream.
  /// Yields one decoded event map per SSE frame (assistant, tool_call,
  /// tool_result, done, error) and closes on the [DONE] sentinel.
  Stream<Map<String, dynamic>> agentStream(String goal, String endpoint,
      {int maxSteps = 8,
      bool allowWrite = false,
      bool allowExec = false,
      String? root,
      String? testCmd}) async* {
    final req = http.Request('POST', Uri.parse('$baseUrl/api/agent'))
      ..headers['Content-Type'] = 'application/json'
      ..body = jsonEncode({
        'goal': goal,
        'endpoint': endpoint,
        'max_steps': maxSteps,
        'allow_write': allowWrite,
        'allow_exec': allowExec,
        'stream': true,
        if (root != null && root.isNotEmpty) 'root': root,
        if (testCmd != null && testCmd.isNotEmpty) 'test_cmd': testCmd,
      });
    final res = await _http.send(req);
    if (res.statusCode != 200) {
      throw GatewayException('gateway returned ${res.statusCode}');
    }
    var buffer = '';
    await for (final chunk in res.stream.transform(utf8.decoder)) {
      buffer += chunk;
      while (true) {
        final sep = buffer.indexOf('\n\n');
        if (sep < 0) break;
        final frame = buffer.substring(0, sep);
        buffer = buffer.substring(sep + 2);
        for (final line in frame.split('\n')) {
          if (!line.startsWith('data: ')) continue;
          final payload = line.substring(6).trim();
          if (payload == '[DONE]') return;
          try {
            yield jsonDecode(payload) as Map<String, dynamic>;
          } catch (_) {
            // A malformed frame is skipped, never fatal to the stream.
          }
        }
      }
    }
  }

  /// GET /api/plugins — every mounted capability, one manifest shape.
  Future<Map<String, dynamic>> plugins() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/plugins'));
    return _decode(r);
  }

  /// GET /api/plugins/probe — spawn a plugin's server, report its real tools.
  Future<Map<String, dynamic>> probePlugin(String name) async {
    final r = await _http.get(Uri.parse(
        '$baseUrl/api/plugins/probe?name=${Uri.encodeQueryComponent(name)}'));
    return _decode(r);
  }

  /// POST /api/plugins/register — register a custom MCP server by argv.
  Future<Map<String, dynamic>> registerPlugin(
      String name, List<String> command,
      {String detail = ''}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/plugins/register'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name, 'command': command, 'detail': detail}),
    );
    return _decode(r);
  }

  /// POST /api/plugins/toggle — enable or disable a custom plugin.
  Future<Map<String, dynamic>> togglePlugin(String name, bool enabled) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/plugins/toggle'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name, 'enabled': enabled}),
    );
    return _decode(r);
  }

  /// POST /api/plugins/remove — remove a custom plugin.
  Future<Map<String, dynamic>> removePlugin(String name) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/plugins/remove'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name}),
    );
    return _decode(r);
  }
}
