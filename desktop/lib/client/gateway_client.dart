import 'dart:convert';
import 'package:http/http.dart' as http;

import '../models/gateway_models.dart';
import '../models/operation_models.dart';
import '../models/workflow_models.dart';
import 'gateway_auth.dart';
import 'gateway_error.dart';
import 'gateway_sse_decoder.dart';
import 'strict_plan_json.dart';
export 'gateway_error.dart';

part 'gateway_streams.dart';
part 'gateway_operations.dart';
part 'gateway_plan_transport.dart';
part 'gateway_creative.dart';
part 'gateway_discovery.dart';

class GatewayClient {
  static const String loopback = 'http://127.0.0.1:8799';

  final String baseUrl;
  final http.Client _http;

  GatewayClient({this.baseUrl = loopback, http.Client? httpClient})
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

  /// GET /api/lanes — the lane roster (live/declared/missing).
  Future<LaneRoster> laneRoster({bool probe = false}) async {
    final r = await _http.get(
      Uri.parse('$baseUrl/api/lanes${probe ? '?probe=true' : ''}'),
    );
    return LaneRoster.fromJson(_decode(r));
  }

  /// GET /api/world — the projected world (spine + root hash + findings).
  Future<WorldDoc> projectedWorld() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/world'));
    return WorldDoc.fromJson(_decode(r));
  }

  /// GET /api/endpoints — the universal router roster (credential presence).
  Future<List<EndpointRow>> endpointRoster() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/endpoints'));
    final body = _decode(r);
    final rows = body['rows'] ?? body['endpoints'] ?? [];
    if (rows is! List) return [];
    return rows
        .map((e) => EndpointRow.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// GET /api/models?endpoint=NAME — one endpoint's model roster.
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

  /// POST /api/relay/start — start a witnessed relay run.
  Future<Map<String, dynamic>> startRelayRun(Map<String, dynamic> task) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/relay/start'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(task),
    );
    return _decode(r);
  }

  /// GET /api/relay/status — a relay run's progress.
  Future<Map<String, dynamic>> relayStatus(String runId) =>
      getJson('/api/relay/status?run_id=${Uri.encodeQueryComponent(runId)}');

  /// GET /api/relay/result — a relay run's verified result once done.
  Future<Map<String, dynamic>> relayResult(String runId) =>
      getJson('/api/relay/result?run_id=${Uri.encodeQueryComponent(runId)}');

  /// GET /api/relay/runs — recent relay runs (survive restart).
  Future<Map<String, dynamic>> relayRuns() => getJson('/api/relay/runs');

  /// GET /api/relay/sessions — saved relay sessions (follow you).
  Future<Map<String, dynamic>> relaySessions() => getJson('/api/relay/sessions');

  /// POST /api/companion — answer locally, escalate the hard slice.
  Future<CompanionResult> companion(String prompt,
      {String? solutionSig,
      String? effort,
      Map<String, dynamic>? authorizedBody}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/companion'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(authorizedBody ?? {
        'prompt': prompt,
        if (solutionSig != null) 'solution_sig': solutionSig,
        if (effort != null) 'effort': effort,
      }),
    );
    return CompanionResult.fromJson(_decode(r));
  }

  /// POST /api/route — route a prompt to a named provider, get a receipt.
  Future<Map<String, dynamic>> route(String prompt, String endpoint,
      {String? model, Map<String, dynamic>? authorizedBody}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/route'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(authorizedBody ?? {
        'prompt': prompt,
        'endpoint': endpoint,
        if (model != null && model.isNotEmpty) 'model': model,
      }),
    );
    return _decode(r);
  }

  /// Generic GET returning decoded JSON, for lightweight read-only routes.
  Future<Map<String, dynamic>> getJson(String path,
      {Duration timeout = const Duration(seconds: 15)}) async {
    final r = await _http.get(Uri.parse('$baseUrl$path')).timeout(timeout);
    return _decode(r);
  }

  /// Generic POST returning decoded JSON, for small parameterless verbs.
  Future<Map<String, dynamic>> postJson(
      String path, Map<String, dynamic> body,
      {Duration timeout = const Duration(seconds: 15)}) async {
    final r = await _http
        .post(
          Uri.parse('$baseUrl$path'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        )
        .timeout(timeout);
    return _decode(r);
  }

  /// POST returning the decoded body whatever the status came back as.
  /// Some routes answer a real finding with a non-200: an evidence packet
  /// that drifted is a 422 whose body IS the verdict, and a suite that
  /// cannot be audited is a 400 that names why. Throwing those away would
  /// report a transport failure where the engine actually answered.
  Future<Map<String, dynamic>> postJsonLenient(
      String path, Map<String, dynamic> body,
      {Duration timeout = const Duration(seconds: 15)}) async {
    final r = await _http
        .post(
          Uri.parse('$baseUrl$path'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        )
        .timeout(timeout);
    return _decodeLenient(r);
  }

  Map<String, dynamic> _decode(http.Response r) {
    if (r.statusCode != 200) {
      throw GatewayException.fromResponse(r.statusCode, r.body);
    }
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

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
