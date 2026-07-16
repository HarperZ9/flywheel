// gateway_client.dart — the typed HTTP client for the Flywheel Python gateway.
//
// The Flutter desktop app is a native CLIENT for the gateway API. The gateway
// (harness/gateway.py, started by `flywheel up`) runs on 127.0.0.1:8799 and
// exposes every route the UI needs as same-origin localhost JSON. This client
// wraps those routes with typed Dart methods so the UI layers never touch raw
// JSON or HTTP.
//
// The gateway is the backend; Flutter is the frontend. The verified-loop,
// receipts, lanes, and corpus-export stay in Python — this client only reads
// and posts to the API.

import 'dart:convert';
import 'package:http/http.dart' as http;

import '../models/gateway_models.dart';
import '../models/workflow_models.dart';

part 'gateway_streams.dart';

class GatewayClient {
  final String baseUrl;
  final http.Client _http;

  GatewayClient({this.baseUrl = 'http://127.0.0.1:8799', http.Client? httpClient})
      : _http = httpClient ?? http.Client();

  /// True if the gateway is reachable (the gateway serves /api/world on GET).
  Future<bool> isAlive({Duration timeout = const Duration(seconds: 2)}) async {
    try {
      final r = await _http
          .get(Uri.parse('$baseUrl/api/world'))
          .timeout(timeout);
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// GET /api/lanes — the lane roster (7 lanes, live/declared/missing).
  Future<LaneRoster> laneRoster({bool probe = false}) async {
    final r = await _http.get(
      Uri.parse('$baseUrl/api/lanes${probe ? '?probe=true' : ''}'),
    );
    return LaneRoster.fromJson(_decode(r));
  }

  /// GET /api/world — the projected world (spine + root hash + findings + cursor).
  Future<WorldDoc> projectedWorld() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/world'));
    return WorldDoc.fromJson(_decode(r));
  }

  /// GET /api/endpoints — the universal router roster (credential presence).
  Future<List<EndpointRow>> endpointRoster() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/endpoints'));
    final body = _decode(r);
    // The roster may be {rows: [...]} or {endpoints: [...]}.
    final rows = body['rows'] ?? body['endpoints'] ?? [];
    if (rows is! List) return [];
    return rows
        .map((e) => EndpointRow.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// GET /api/endpoints/health — live health probe of local tiers.
  Future<Map<String, dynamic>> endpointHealth() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/endpoints/health'));
    return _decode(r);
  }

  /// GET /api/router/stats — observed per-provider success rate + cost.
  Future<Map<String, dynamic>> routerStats() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/router/stats'));
    return _decode(r);
  }

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

  /// POST /api/companion — answer locally, escalate the hard slice.
  Future<CompanionResult> companion(String prompt, {String? solutionSig}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/companion'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'prompt': prompt,
        if (solutionSig != null) 'solution_sig': solutionSig,
      }),
    );
    return CompanionResult.fromJson(_decode(r));
  }

  /// POST /api/route — route a prompt to a named provider, get a receipt.
  Future<Map<String, dynamic>> route(String prompt, String endpoint) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/route'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'prompt': prompt, 'endpoint': endpoint}),
    );
    return _decode(r);
  }

  /// POST /api/discourse — drive the chorus satellite over a gathered comment
  /// corpus (a gather corpus directory or a JSON row list) and return chorus's
  /// own weighted, clustered, re-checkable discourse digest verbatim.
  Future<Map<String, dynamic>> discourse(String corpus) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/discourse'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'corpus': corpus}),
    );
    return _decode(r);
  }

  /// POST /api/discourse/corpora — discover gather corpora under a root, so a
  /// gathered run can be picked as a discourse source without typing its path.
  Future<Map<String, dynamic>> discourseCorpora(String root) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/discourse/corpora'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'root': root}),
    );
    return _decode(r);
  }

  /// POST /api/discourse/digests — what the chorus daemon has synthesized on a
  /// schedule, newest first, so the app can show it without re-running anything.
  Future<Map<String, dynamic>> discourseDigests(String store, {int limit = 20}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/discourse/digests'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'store': store, 'limit': limit}),
    );
    return _decode(r);
  }

  /// POST /api/forge — turn a plain goal into a structured prompt with gates.
  Future<Map<String, dynamic>> forge(String goal,
      {String? context, List<String>? examples}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/forge'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'goal': goal,
        if (context != null) 'context': context,
        if (examples != null) 'examples': examples,
      }),
    );
    return _decode(r);
  }

  /// POST /api/agent — run a gated, witnessed tool loop (non-streaming).
  /// `root` scopes the run to an open workspace; the engine refuses a root
  /// that is not an existing directory.
  Future<Map<String, dynamic>> agent(String goal, String endpoint,
      {int maxSteps = 6,
      bool allowWrite = false,
      bool allowExec = false,
      String? root,
      String? testCmd}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/agent'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'goal': goal,
        'endpoint': endpoint,
        'max_steps': maxSteps,
        'allow_write': allowWrite,
        'allow_exec': allowExec,
        if (root != null && root.isNotEmpty) 'root': root,
        if (testCmd != null && testCmd.isNotEmpty) 'test_cmd': testCmd,
      }),
    );
    return _decode(r);
  }

  /// Generic GET returning decoded JSON, for lightweight read-only routes.
  Future<Map<String, dynamic>> getJson(String path) async {
    final r = await _http.get(Uri.parse('$baseUrl$path'));
    return _decode(r);
  }

  /// GET /api/receipts — the receipts ledger (catalog + proof envelopes).
  Future<ReceiptsLedger> receipts() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/receipts'));
    return ReceiptsLedger.fromJson(_decode(r));
  }

  /// GET /api/profiles — the profile manifests over the one substrate.
  Future<List<ProfileManifest>> profiles() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/profiles'));
    final body = _decode(r);
    return ((body['profiles'] ?? []) as List)
        .map((e) => ProfileManifest.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// GET /api/workflows — workflow definitions plus recent runs.
  Future<WorkflowRoster> workflows() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/workflows'));
    return WorkflowRoster.fromJson(_decode(r));
  }

  /// POST /api/workflow — run a staged workflow over any endpoint. `root`
  /// scopes the run to a workspace; the engine refuses a missing directory.
  Future<WorkflowRun> runWorkflow({
    required String workflow,
    required String goal,
    required String endpoint,
    String? profile,
    bool allowWrite = false,
    bool allowExec = false,
    String? testCmd,
    String? root,
  }) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/workflow'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'workflow': workflow,
        'goal': goal,
        'endpoint': endpoint,
        if (profile != null) 'profile': profile,
        'allow_write': allowWrite,
        'allow_exec': allowExec,
        if (testCmd != null && testCmd.isNotEmpty) 'test_cmd': testCmd,
        if (root != null && root.isNotEmpty) 'root': root,
      }),
    );
    return WorkflowRun.fromJson(_decode(r));
  }

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
    final r = await _http.get(Uri.parse('$baseUrl/api/memory/list?limit=$limit'));
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

  Map<String, dynamic> _decode(http.Response r) {
    if (r.statusCode != 200) {
      throw GatewayException(
          'gateway returned ${r.statusCode}: ${r.body.substring(0, r.body.length.clamp(0, 200))}');
    }
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  void close() => _http.close();
}

class GatewayException implements Exception {
  final String message;
  GatewayException(this.message);
  @override
  String toString() => 'GatewayException: $message';
}
