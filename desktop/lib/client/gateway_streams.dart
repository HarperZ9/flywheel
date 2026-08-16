part of 'gateway_client.dart';

extension GatewayStreamsAndPlugins on GatewayClient {
  /// POST /v1/chat/completions with stream:true — a conversational turn over any
  /// endpoint in the roster. Yields `{type:'delta', content:'…'}` as the answer
  /// arrives and a final `{type:'done', receipt:{…}}` carrying the turn's
  /// re-derivable receipt. Invalid framing closes observation as unknown.
  Stream<Map<String, dynamic>> chatStream(
      List<Map<String, String>> messages, String model,
      {Map<String, dynamic>? authorizedBody}) async* {
    final req = http.Request('POST', Uri.parse('$baseUrl/v1/chat/completions'))
      ..headers['Content-Type'] = 'application/json'
      ..body = jsonEncode(authorizedBody ??
          {'model': model, 'messages': messages, 'stream': true});
    final res = await _http.send(req);
    if (res.statusCode != 200) {
      throw GatewayException('gateway returned ${res.statusCode}');
    }
    const decoder =
        GatewaySseDecoder(requireIds: false, requireTerminal: false);
    await for (final event in res.stream.transform(decoder)) {
      if (event.isDone) return;
      final obj = event.data as Map<String, dynamic>;
      final choices = obj['choices'];
      final delta =
          choices is List && choices.isNotEmpty && choices.first is Map
              ? (choices.first as Map)['delta']
              : null;
      final content = delta is Map ? delta['content'] : null;
      if (content is String && content.isNotEmpty) {
        yield {'type': 'delta', 'content': content};
      }
      if (obj['x_receipt'] is Map<String, dynamic>) {
        yield {'type': 'done', 'receipt': obj['x_receipt']};
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
    final q =
        domain == null ? '' : '?domain=${Uri.encodeQueryComponent(domain)}';
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

  /// POST /api/lanes/install — install one lane on request. A down lane
  /// finally has remediation from the surface that reports it down.
  Future<Map<String, dynamic>> installLane(String name,
      {String profile = 'package'}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/lanes/install'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name, 'profile': profile}),
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
  Future<Map<String, dynamic>> addProject(String root,
      {String name = ''}) async {
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
}
