// Typed loopback client. Durable agent operations live in the gateway.

import 'dart:convert';
import 'package:http/http.dart' as http;

import '../models/gateway_models.dart';
import '../models/operation_models.dart';
import '../models/workflow_models.dart';
import 'gateway_auth.dart';
import 'gateway_error.dart';
import 'gateway_sse_decoder.dart';

export 'gateway_error.dart';

part 'gateway_streams.dart';
part 'gateway_operations.dart';

class GatewayClient {
  final String baseUrl;
  final http.Client _http;

  /// The default client presents the gateway's bearer token on every request
  /// (see gateway_auth.dart). The gateway rejects an unauthenticated call with
  /// 401, so a client without the header reports a healthy engine as offline.
  /// An injected [httpClient] is used verbatim, which keeps tests in control of
  /// their own headers.
  GatewayClient(
      {this.baseUrl = 'http://127.0.0.1:8799', http.Client? httpClient})
      : _http = httpClient ?? AuthedClient(http.Client());

  /// True if the gateway is reachable (the gateway serves /api/world on GET).
  Future<bool> isAlive({Duration timeout = const Duration(seconds: 2)}) async {
    try {
      final r =
          await _http.get(Uri.parse('$baseUrl/api/world')).timeout(timeout);
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

  /// GET /api/models?endpoint=NAME — one endpoint's model roster. The
  /// default is flagged; a failed listing degrades to an honest reason.
  Future<Map<String, dynamic>> models(String endpoint) =>
      getJson('/api/models?endpoint=${Uri.encodeQueryComponent(endpoint)}');

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

  /// POST /api/typeface — mint a parametric face; outlines + receipt back.
  Future<Map<String, dynamic>> typefaceMint(
      Map<String, dynamic> params, int seed) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/typeface'),
      headers: {'Content-Type': 'application/json'},
      // every mint carries its font file, so the face is wearable the
      // moment it exists
      body: jsonEncode({
        'params': params,
        'seed': seed,
        'ttf': true,
        'family': 'Zentropy Mint $seed',
      }),
    );
    return _decode(r);
  }

  /// POST /api/typeface/publish — file a minted face in the witnessed gallery.
  Future<Map<String, dynamic>> typefacePublish(
      Map<String, dynamic> params, int seed,
      {String family = ''}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/typeface/publish'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'params': params,
        'seed': seed,
        if (family.isNotEmpty) 'family': family,
      }),
    );
    return _decode(r);
  }

  /// GET /api/typeface/gallery — the marketplace listing (metadata only).
  Future<Map<String, dynamic>> typefaceGallery({int limit = 60}) =>
      getJson('/api/typeface/gallery?limit=$limit');

  /// GET /api/typeface/face — one published face with its .ttf bytes.
  Future<Map<String, dynamic>> typefaceFace(String eid) =>
      getJson('/api/typeface/face?eid=$eid');

  /// POST /api/typeface/variable — the family's weights as ONE variable font
  /// with a wght axis; the response carries the .ttf and a receipt.
  Future<Map<String, dynamic>> typefaceVariable(
      Map<String, dynamic> params, int seed) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/typeface/variable'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'params': params,
        'seed': seed,
        'family': 'Zentropy Mint $seed',
      }),
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

  /// POST /api/companion — answer locally, escalate the hard slice.
  Future<CompanionResult> companion(String prompt,
      {String? solutionSig}) async {
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
  /// [model] overrides the endpoint's default model; null keeps the default.
  Future<Map<String, dynamic>> route(String prompt, String endpoint,
      {String? model}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/route'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'prompt': prompt,
        'endpoint': endpoint,
        if (model != null && model.isNotEmpty) 'model': model,
      }),
    );
    return _decode(r);
  }

  /// POST /api/eval/run — run a real eval through [endpoint] and get back a
  /// sealed, offline-verifiable receipt. [model] overrides the endpoint's
  /// default model (null/empty keeps it); [n] is the task count (1..5, capped
  /// by the engine). A provider or credential error is returned as its JSON
  /// body, not thrown, so the UI surfaces the reason as an honest null instead
  /// of a dead exception.
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

  /// POST /api/eval/verify — re-check a receipt offline. The verdict (MATCH /
  /// TAMPERED / UNVERIFIABLE) is the answer, so the route always returns 200 and
  /// a corrupted receipt is a first-class result, never an HTTP error.
  Future<Map<String, dynamic>> evalVerify(Map<String, dynamic> receipt) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/eval/verify'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'receipt': receipt}),
    );
    return _decodeLenient(r);
  }

  /// POST /api/audit/run — review a completed [workReceipt] and seal the review
  /// into an audit receipt CHAINED onto it (prev_receipt_sha256 = the work
  /// receipt's seal hex). The reviewer is cheap: it runs deterministically with
  /// no model, and adds a narrative only when [endpoint] is supplied and
  /// reachable; offline degrades the summary to an honest null, never an error.
  /// [artifact] is the optional work text/summary to review. A bad request is
  /// returned as its JSON body, not thrown.
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

  /// POST /api/audit/verify — re-check an audit receipt offline. With
  /// [workReceipt] supplied it ALSO confirms the chain link back to the work (a
  /// wrong prev is CHAIN_BROKEN). The verdict (MATCH / TAMPERED / UNVERIFIABLE)
  /// is the answer, so the route always returns 200 and a corrupted receipt is a
  /// first-class result, never an HTTP error.
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

  /// GET /api/usage — the signed usage-metering session summary. Rolls the
  /// emitted usage receipts into token totals, per-endpoint splits, a priced
  /// total that sums ONLY the receipts carrying a dollar amount, an unpriced
  /// count, and the receipts themselves so the UI re-verifies each one offline.
  /// Tokens are provider-reported when the provider returned a usage object,
  /// else a labeled estimate; the dollar figure is a table lookup, never a
  /// provider-billed number.
  Future<Map<String, dynamic>> usageSummary() => getJson('/api/usage');

  /// POST /api/usage/verify — re-check one usage receipt offline. The verdict
  /// (MATCH / TAMPERED / UNVERIFIABLE) is the answer, so the route always returns
  /// 200 and a corrupted receipt is a first-class result, never an HTTP error.
  Future<Map<String, dynamic>> usageVerify(Map<String, dynamic> receipt) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/usage/verify'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'receipt': receipt}),
    );
    return _decodeLenient(r);
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
  Future<Map<String, dynamic>> discourseDigests(String store,
      {int limit = 20}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/discourse/digests'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'store': store, 'limit': limit}),
    );
    return _decode(r);
  }

  /// POST /api/forge/recheck — has an arm drifted since the forge sealed it?
  Future<Map<String, dynamic>> forgeRecheck(String prpId) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/forge/recheck'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'prp_id': prpId}),
    );
    return _decode(r);
  }

  /// POST /api/studio/poster — plate + minted face + copy under one receipt.
  Future<Map<String, dynamic>> studioPoster(String title,
      {String subtitle = '',
      String format = 'poster',
      int seed = 58,
      String ground = 'dark',
      bool accent = true,
      Map<String, dynamic>? faceParams}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/studio/poster'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'title': title,
        'subtitle': subtitle,
        'format': format,
        'seed': seed,
        'ground': ground,
        'accent': accent,
        if (faceParams != null) 'face_params': faceParams,
      }),
    );
    return _decode(r);
  }

  /// POST /api/telos/kernel — run a bridged telos creative kernel; the
  /// answer (points, bounds, receipt hashes) is the kernel's own.
  Future<Map<String, dynamic>> telosKernel(
      String kernel, Map<String, dynamic> args) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/telos/kernel'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'kernel': kernel, 'args': args}),
    );
    return _decode(r);
  }

  /// POST /api/telos/raster — dither or pixel-sort over a plate or PNG;
  /// the receipt carries the kernel's own hashes.
  Future<Map<String, dynamic>> telosRaster(String kernel,
      {Map<String, dynamic>? source, Map<String, dynamic>? args}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/telos/raster'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'kernel': kernel,
        if (source != null) 'source': source,
        if (args != null) 'args': args,
      }),
    );
    return _decode(r);
  }

  /// POST /api/studio/graph — a branching creative DAG; every node's chain
  /// folds its inputs' chains, so the graph id witnesses everything.
  Future<Map<String, dynamic>> studioGraph(List<Map<String, dynamic>> nodes,
      List<Map<String, dynamic>> edges) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/studio/graph'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'nodes': nodes, 'edges': edges}),
    );
    return _decode(r);
  }

  /// POST /api/studio/pipeline — ordered creative stages, one chained
  /// receipt; the pipeline id witnesses the whole line in order.
  Future<Map<String, dynamic>> studioPipeline(
      List<Map<String, dynamic>> stages) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/studio/pipeline'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'stages': stages}),
    );
    return _decode(r);
  }

  /// POST /api/studio/brandkit — one seed + a name -> a whole identity.
  Future<Map<String, dynamic>> brandKit(String name,
      {String tagline = '',
      int seed = 58,
      Map<String, dynamic>? faceParams}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/studio/brandkit'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'name': name,
        'tagline': tagline,
        'seed': seed,
        if (faceParams != null) 'face_params': faceParams,
      }),
    );
    return _decode(r);
  }

  /// POST /api/studio/sound — the seeded chime study; the score is the receipt.
  Future<Map<String, dynamic>> studioSound(
      {int seed = 58, double duration = 24, double root = 220}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/studio/sound'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'seed': seed, 'duration': duration, 'root': root}),
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

  /// Generic GET returning decoded JSON, for lightweight read-only routes.
  Future<Map<String, dynamic>> getJson(String path) async {
    final r = await _http.get(Uri.parse('$baseUrl$path'));
    return _decode(r);
  }

  /// Generic POST returning decoded JSON, for small parameterless verbs.
  Future<Map<String, dynamic>> postJson(
      String path, Map<String, dynamic> body) async {
    final r = await _http.post(
      Uri.parse('$baseUrl$path'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    return _decode(r);
  }

  /// GET /api/receipts — the receipts ledger (catalog + proof envelopes).
  Future<ReceiptsLedger> receipts() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/receipts'));
    return ReceiptsLedger.fromJson(_decode(r));
  }

  /// GET /api/receipts/proof — prove one receipt (a 64-hex leaf) is in the
  /// Merkle log, with the audit path anyone can re-walk offline.
  Future<Map<String, dynamic>> receiptsProof(String leaf) async {
    final r = await _http.get(Uri.parse(
        '$baseUrl/api/receipts/proof?leaf=${Uri.encodeQueryComponent(leaf)}'));
    return _decode(r);
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

  /// GET /api/lessons -- the organizational learning loop: count, feed, verify.
  Future<Map<String, dynamic>> lessons() => getJson('/api/lessons');

  /// GET /api/lessons/patterns -- recurring patterns for human admission.
  Future<Map<String, dynamic>> lessonsPatterns() =>
      getJson('/api/lessons/patterns');

  /// POST /api/lessons/admit -- transition a lesson to admitted.
  Future<Map<String, dynamic>> lessonAdmit(String lessonId) =>
      postJson('/api/lessons/admit', {'lesson_id': lessonId});

  /// POST /api/lessons/retire -- transition a lesson to retired.
  Future<Map<String, dynamic>> lessonRetire(String lessonId) =>
      postJson('/api/lessons/retire', {'lesson_id': lessonId});

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

  Map<String, dynamic> _decode(http.Response r) {
    if (r.statusCode != 200) {
      throw GatewayException.fromResponse(r.statusCode, r.body);
    }
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  /// Decode a JSON body regardless of status. Used by routes whose non-200
  /// responses still carry a meaningful body (an honest error, a refusal
  /// verdict) the UI must show rather than throw away.
  Map<String, dynamic> _decodeLenient(http.Response r) {
    try {
      final v = jsonDecode(r.body);
      if (v is Map<String, dynamic>) return v;
      return {'error': 'unexpected response shape (${r.statusCode})'};
    } catch (_) {
      return {'error': 'gateway returned ${r.statusCode}'};
    }
  }

  void close() => _http.close();
}
