// Typed browser-control API: what a run was allowed to drive, and what
// it actually did.
//
// GET /api/browser lists the sessions under this run root and names the
// driver bound to the engine, or null when none is.
// GET /api/browser/{run_id} reads one session: the policy fixed at its
// first record, every verdict since, and the counts over them.
//
// Both verbs are reads, and that is deliberate. A session's policy is
// its chain's first record, so opening one from a console would fix the
// rules for a run from outside the run. Acts belong to the run that was
// given the policy; this client watches.
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'gateway_auth.dart';
import 'gateway_error.dart';

class BrowserApi {
  final String baseUrl;
  final http.Client _http;

  BrowserApi({String? baseUrl, http.Client? httpClient})
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

  /// GET /api/browser -- every session, and the bound driver if there is
  /// one. A null driver means the engine decided and recorded and moved
  /// no screen, which is a supported way to run rather than a fault.
  Future<Map<String, dynamic>> roster() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/browser'));
    return _decode(r);
  }

  /// GET /api/browser/{run_id} -- one session's policy, verdicts, counts,
  /// and whether its chain still verifies.
  ///
  /// The id goes through unrepaired. The engine checks it rather than
  /// stripping it, so a name that would reach another session's history
  /// is refused instead of quietly resolving to a third one.
  Future<Map<String, dynamic>> session(String runId) async {
    final r = await _http
        .get(Uri.parse('$baseUrl/api/browser/${Uri.encodeComponent(runId)}'));
    return _decode(r);
  }
}
