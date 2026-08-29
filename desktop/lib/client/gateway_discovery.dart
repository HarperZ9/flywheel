part of 'gateway_client.dart';

extension GatewayDiscovery on GatewayClient {
  /// GET /api/instruments — the evaluation-engineering register.
  Future<Map<String, dynamic>> instruments() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/instruments'));
    return _decode(r);
  }

  /// GET /api/academy — the curriculum derived from the live code.
  Future<Map<String, dynamic>> academy() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/academy'));
    return _decode(r);
  }

  /// Run a lesson's declared GET check against the gateway. Returns the
  /// status code and a short body excerpt so the verdict stays inspectable.
  Future<(int, String)> runLessonCheck(String path) async {
    final r = await _http.get(Uri.parse('$baseUrl$path'));
    final body = r.body.length > 240 ? '${r.body.substring(0, 240)}…' : r.body;
    return (r.statusCode, body);
  }

  /// POST /api/academy/complete — bind a passed comprehension receipt to a
  /// lesson; completion is a re-checkable receipt, never prose.
  Future<Map<String, dynamic>> academyComplete(
      String lessonId, String comprehensionEid) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/academy/complete'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(
          {'lesson_id': lessonId, 'comprehension_eid': comprehensionEid}),
    );
    return _decode(r);
  }

  /// POST /api/learn/animate — a lesson rendered as a runnable manim scene.
  Future<Map<String, dynamic>> learnAnimate(Map<String, dynamic> lesson) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/learn/animate'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'lesson': lesson}),
    );
    return _decode(r);
  }

  /// POST /api/eval/run — run a real eval through [endpoint] and get back a
  /// sealed, offline-verifiable receipt.
  Future<Map<String, dynamic>> evalRun(String endpoint,
      {String? model, int n = 3}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/eval/run'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'endpoint': endpoint,
        if (model != null && model.isNotEmpty) 'model': model,
        'n': n,
      }),
    );
    return _decodeLenient(r);
  }

  /// POST /api/eval/verify — re-check a receipt offline.
  Future<Map<String, dynamic>> evalVerify(Map<String, dynamic> receipt) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/eval/verify'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'receipt': receipt}),
    );
    return _decodeLenient(r);
  }

  /// POST /api/audit/run — review a completed work receipt and seal the review
  /// into an audit receipt chained onto it.
  Future<Map<String, dynamic>> auditRun(Map<String, dynamic> workReceipt,
      {String? endpoint, String? model, String? artifact}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/audit/run'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'work_receipt': workReceipt,
        if (endpoint != null && endpoint.isNotEmpty) 'endpoint': endpoint,
        if (model != null && model.isNotEmpty) 'model': model,
        if (artifact != null && artifact.isNotEmpty) 'artifact': artifact,
      }),
    );
    return _decodeLenient(r);
  }

  /// POST /api/audit/verify — re-check an audit receipt offline.
  Future<Map<String, dynamic>> auditVerify(Map<String, dynamic> auditReceipt,
      {Map<String, dynamic>? workReceipt}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/audit/verify'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'audit_receipt': auditReceipt,
        if (workReceipt != null) 'work_receipt': workReceipt,
      }),
    );
    return _decodeLenient(r);
  }

  /// GET /api/usage — the signed usage-metering session summary.
  Future<Map<String, dynamic>> usageSummary() => getJson('/api/usage');

  /// POST /api/usage/verify — re-check one usage receipt offline.
  Future<Map<String, dynamic>> usageVerify(Map<String, dynamic> receipt) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/usage/verify'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'receipt': receipt}),
    );
    return _decodeLenient(r);
  }

  /// POST /api/discourse — drive the chorus satellite over a gathered corpus.
  Future<Map<String, dynamic>> discourse(String corpus) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/discourse'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'corpus': corpus}),
    );
    return _decode(r);
  }

  /// POST /api/discourse/corpora — discover gather corpora under a root.
  Future<Map<String, dynamic>> discourseCorpora(String root) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/discourse/corpora'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'root': root}),
    );
    return _decode(r);
  }

  /// POST /api/discourse/digests — synthesized chorus digests, newest first.
  Future<Map<String, dynamic>> discourseDigests(String store,
      {int limit = 20}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/discourse/digests'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'store': store, 'limit': limit}),
    );
    return _decode(r);
  }

  /// GET /api/science/runs — persisted science history, chain-reverified.
  Future<Map<String, dynamic>> scienceRuns({int limit = 20}) =>
      getJson('/api/science/runs?limit=$limit');

  /// GET /api/science/run — one stored science run by chain prefix.
  Future<Map<String, dynamic>> scienceRunDetail(String chain) =>
      getJson('/api/science/run?chain=$chain');

  /// GET /api/workflow/run — one stored per-stage trace, chain-reverified.
  Future<Map<String, dynamic>> workflowRunDetail(String chain) =>
      getJson('/api/workflow/run?chain=$chain');

  /// GET /api/agent/runs — persisted agent runs, content-addressed.
  Future<Map<String, dynamic>> agentRuns({int limit = 20}) =>
      getJson('/api/agent/runs?limit=$limit');

  /// GET /api/agent/run — one stored agent run with its trace events.
  Future<Map<String, dynamic>> agentRunDetail(String id) =>
      getJson('/api/agent/run?id=$id');

  /// GET /api/lessons — the organizational learning loop.
  Future<Map<String, dynamic>> lessons() => getJson('/api/lessons');

  /// GET /api/lessons/patterns — recurring patterns for human admission.
  Future<Map<String, dynamic>> lessonsPatterns() =>
      getJson('/api/lessons/patterns');

  /// POST /api/lessons/admit — transition a lesson to admitted.
  Future<Map<String, dynamic>> lessonAdmit(String lessonId) =>
      postJson('/api/lessons/admit', {'lesson_id': lessonId});

  /// POST /api/lessons/retire — transition a lesson to retired.
  Future<Map<String, dynamic>> lessonRetire(String lessonId) =>
      postJson('/api/lessons/retire', {'lesson_id': lessonId});

  /// GET /api/memory — durable memory stats.
  Future<Map<String, dynamic>> memoryStats() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/memory'));
    return _decode(r);
  }

  /// POST /api/memory/recall — verbatim recall from the fold index.
  Future<Map<String, dynamic>> memoryRecall(String query,
      {int topK = 5}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/memory/recall'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'query': query, 'top_k': topK}),
    );
    return _decode(r);
  }

  /// GET /api/memory/list — browse stored spans verbatim (no query).
  Future<Map<String, dynamic>> memoryList({int limit = 20}) async {
    final r =
        await _http.get(Uri.parse('$baseUrl/api/memory/list?limit=$limit'));
    return _decode(r);
  }

  /// POST /api/memory/note — store a durable content-addressed note.
  Future<Map<String, dynamic>> memoryNote(String content) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/memory/note'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'content': content}),
    );
    return _decode(r);
  }

  /// GET /api/training/status — read-only 32B training lane status.
  Future<Map<String, dynamic>> trainingStatus() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/training/status'));
    return _decode(r);
  }

  /// GET /api/session-tokens — active scoped, time-bounded agent tokens.
  Future<Map<String, dynamic>> sessionTokens() => getJson('/api/session-tokens');

  /// POST /api/session-tokens/revoke — revoke one session token by ref.
  Future<Map<String, dynamic>> sessionTokenRevoke(String tokenRef) =>
      postJson('/api/session-tokens/revoke', {'token_ref': tokenRef});

  /// GET /api/workflows — workflow definitions plus recent runs.
  Future<WorkflowRoster> workflows() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/workflows'));
    return WorkflowRoster.fromJson(_decode(r));
  }

  /// GET /api/profiles — the profile manifests over the one substrate.
  Future<List<ProfileManifest>> profiles() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/profiles'));
    final body = _decode(r);
    return ((body['profiles'] ?? []) as List)
        .map((e) => ProfileManifest.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// GET /api/receipts — the receipts ledger (catalog + proof envelopes).
  Future<ReceiptsLedger> receipts() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/receipts'));
    return ReceiptsLedger.fromJson(_decode(r));
  }

  /// GET /api/receipts/proof — prove one receipt is in the Merkle log.
  Future<Map<String, dynamic>> receiptsProof(String leaf) async {
    final r = await _http.get(Uri.parse(
        '$baseUrl/api/receipts/proof?leaf=${Uri.encodeQueryComponent(leaf)}'));
    return _decode(r);
  }
}
