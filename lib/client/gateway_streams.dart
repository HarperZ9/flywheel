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

  /// POST /v1/chat/completions with stream:true — a conversational turn over any
  /// endpoint in the roster. Yields `{type:'delta', content:'…'}` as the answer
  /// arrives and a final `{type:'done', receipt:{…}}` carrying the turn's
  /// re-derivable receipt. Malformed frames are skipped, never fatal.
  Stream<Map<String, dynamic>> chatStream(
      List<Map<String, String>> messages, String model) async* {
    final req = http.Request('POST', Uri.parse('$baseUrl/v1/chat/completions'))
      ..headers['Content-Type'] = 'application/json'
      ..body = jsonEncode({'model': model, 'messages': messages, 'stream': true});
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
            final obj = jsonDecode(payload) as Map<String, dynamic>;
            final choices = obj['choices'];
            final delta = (choices is List && choices.isNotEmpty)
                ? (choices.first as Map<String, dynamic>)['delta']
                : null;
            final content = (delta is Map) ? delta['content'] : null;
            if (content is String && content.isNotEmpty) {
              yield {'type': 'delta', 'content': content};
            }
            if (obj['x_receipt'] is Map<String, dynamic>) {
              yield {'type': 'done', 'receipt': obj['x_receipt']};
            }
          } catch (_) {
            // a malformed frame is skipped, never fatal to the stream
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

  /// GET /api/parity — the capability matrix, audited at read time.
  Future<Map<String, dynamic>> parity() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/parity'));
    return _decode(r);
  }

  /// GET /api/projects — the registered project/directory roster.
  Future<Map<String, dynamic>> projects() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/projects'));
    return _decode(r);
  }

  /// GET /api/uplift — persisted bare-vs-wrapped bench runs (read-only).
  Future<Map<String, dynamic>> upliftSummary() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/uplift'));
    return _decode(r);
  }

  /// GET /api/feeds — cross-domain live feeds through the gather lane.
  Future<Map<String, dynamic>> feeds({String? domain}) async {
    final q = domain == null
        ? ''
        : '?domain=${Uri.encodeQueryComponent(domain)}';
    final r = await _http.get(Uri.parse('$baseUrl/api/feeds$q'));
    return _decode(r);
  }

  /// POST /api/attest — ownership made checkable: the sign-off binds to the
  /// run's checkpoint and to exactly what was walked; the engine computes
  /// coverage and persists the attestation into the verifiable store.
  Future<Map<String, dynamic>> attest(
      {required Map<String, dynamic> run,
      required List<String> reviewedFiles,
      String note = '',
      String reviewer = ''}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/attest'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'run': run,
        'reviewed_files': reviewedFiles,
        if (note.isNotEmpty) 'note': note,
        if (reviewer.isNotEmpty) 'reviewer': reviewer,
      }),
    );
    return _decode(r);
  }

  /// POST /api/snapshot — the citation, frozen: the page's bytes fetched,
  /// hashed, and stored so the reference outlives the live web.
  Future<Map<String, dynamic>> snapshotUrl(String url) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/snapshot'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'url': url}),
    );
    return _decode(r);
  }

  /// POST /api/explain — the teach-back graded mechanically: the explanation
  /// must name the changed files, cover the key changed identifiers, and be
  /// in your own words (pasting the diff back cannot pass). The receipt
  /// lands in the comprehension ledger.
  Future<Map<String, dynamic>> explain(String diff, String explanation,
      {double threshold = 0.6, String reviewer = ''}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/explain'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'diff': diff,
        'explanation': explanation,
        'threshold': threshold,
        if (reviewer.isNotEmpty) 'reviewer': reviewer,
      }),
    );
    return _decode(r);
  }

  /// POST /api/retention — bank an unaided retest outcome, linked to the
  /// original evidence in the verifiable store.
  Future<Map<String, dynamic>> retentionRecord(String original, bool passed,
      {String note = ''}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/retention'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'original': original,
        'passed': passed,
        if (note.isNotEmpty) 'note': note,
      }),
    );
    return _decode(r);
  }

  /// POST /api/science — evidence, gated spec, witnessed claim verdicts.
  Future<Map<String, dynamic>> science(String question,
      {List<Map<String, String>>? claims,
      List<Map<String, dynamic>>? measurements,
      int maxSources = 4}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/science'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'question': question,
        if (claims != null && claims.isNotEmpty) 'claims': claims,
        if (measurements != null && measurements.isNotEmpty)
          'measurements': measurements,
        'max_sources': maxSources,
      }),
    );
    return _decode(r);
  }

  /// POST /api/projects/add — register a project directory.
  Future<Map<String, dynamic>> addProject(String root, {String name = ''}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/projects/add'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'root': root, if (name.isNotEmpty) 'name': name}),
    );
    return _decode(r);
  }

  /// POST /api/projects/remove — unregister a project directory.
  Future<Map<String, dynamic>> removeProject(String root) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/projects/remove'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'root': root}),
    );
    return _decode(r);
  }

  /// POST /api/index — drive the index engine over a project root. `view` is
  /// summary | map | graph | symbols.
  Future<Map<String, dynamic>> indexProject(String root,
      {String view = 'summary'}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/index'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'root': root, 'view': view}),
    );
    return _decode(r);
  }

  /// POST /api/lint — the native receipted linter over a project root.
  Future<Map<String, dynamic>> lintProject(String root,
      {List<String>? paths}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/lint'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'root': root, if (paths != null) 'paths': paths}),
    );
    return _decode(r);
  }

  /// GET /api/store — the verifiable substrate stats.
  Future<Map<String, dynamic>> storeStats() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/store'));
    return _decode(r);
  }

  /// GET /api/store/verify — re-check the hash-chained audit ledger.
  Future<Map<String, dynamic>> storeVerify() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/store/verify'));
    return _decode(r);
  }

  /// GET /api/store/audit — the audit tail.
  Future<Map<String, dynamic>> storeAudit({int n = 50}) async {
    final r = await _http.get(Uri.parse('$baseUrl/api/store/audit?n=$n'));
    return _decode(r);
  }

  /// POST /api/lsp — editor intelligence over any user-named LSP server.
  /// Sends the live buffer so unsaved edits are visible to the server.
  Future<Map<String, dynamic>> lspQuery({
    required List<String> command,
    required String root,
    required String file,
    required String text,
    required String languageId,
    required String method,
    required int line,
    required int character,
  }) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/lsp'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'command': command,
        'root': root,
        'file': file,
        'text': text,
        'language_id': languageId,
        'method': method,
        'line': line,
        'character': character,
      }),
    );
    return _decode(r);
  }

  /// GET /api/keychain — credential names + presence/source, never values.
  Future<Map<String, dynamic>> keychainRoster() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/keychain'));
    return _decode(r);
  }

  /// POST /api/keychain/set — store a secret in the OS keychain. The value
  /// travels loopback-only, once, and is never echoed back.
  Future<Map<String, dynamic>> keychainSet(String name, String value) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/keychain/set'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name, 'value': value}),
    );
    return _decode(r);
  }

  /// POST /api/keychain/delete — remove a stored secret.
  Future<Map<String, dynamic>> keychainDelete(String name) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/keychain/delete'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name}),
    );
    return _decode(r);
  }

  /// GET /api/marketplace — the curated catalog over the plugin registry.
  Future<Map<String, dynamic>> marketplace() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/marketplace'));
    return _decode(r);
  }

  /// POST /api/marketplace/install — register a catalog entry.
  Future<Map<String, dynamic>> installFromCatalog(String name) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/marketplace/install'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name}),
    );
    return _decode(r);
  }

  /// POST /api/marketplace/add — save a user entry into the catalog.
  /// `requires` lists env var NAMES only; the engine refuses values.
  Future<Map<String, dynamic>> marketplaceAdd(
      String name, List<String> command,
      {String detail = '', List<String> requires = const []}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/marketplace/add'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'name': name,
        'command': command,
        'detail': detail,
        'requires': requires,
      }),
    );
    return _decode(r);
  }

  /// POST /api/marketplace/remove — drop a user catalog entry.
  Future<Map<String, dynamic>> marketplaceRemove(String name) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/marketplace/remove'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name}),
    );
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
