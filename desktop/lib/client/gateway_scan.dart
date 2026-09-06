// Typed code-scan API: two verbs on one route.
//
// GET /api/scan/vulnerabilities reads the last scan, the chain verdict
// on the history, and a fresh re-check of that record against the tree.
// POST runs a scan and appends it.
//
// The tree scanned is the repository the engine already serves. It is
// not a field here, and adding one would turn a security surface into a
// file-read primitive. Suppressions are read engine-side from a file an
// operator edits, so there is no way to quiet a finding from a request.
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'gateway_auth.dart';
import 'gateway_error.dart';

class ScanApi {
  final String baseUrl;
  final http.Client _http;

  ScanApi({String? baseUrl, http.Client? httpClient})
      : baseUrl = baseUrl ?? 'http://127.0.0.1:8799',
        _http = httpClient ?? AuthedClient(http.Client());

  Map<String, dynamic> _body(http.Response r) {
    final decoded = jsonDecode(utf8.decode(r.bodyBytes));
    return decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
  }

  Map<String, dynamic> _decode(http.Response r) {
    if (r.statusCode >= 400) {
      throw GatewayException.fromResponse(
          r.statusCode, utf8.decode(r.bodyBytes));
    }
    return _body(r);
  }

  /// GET /api/scan/vulnerabilities -- the last scan and both verdicts.
  Future<Map<String, dynamic>> latest() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/scan/vulnerabilities'));
    return _decode(r);
  }

  /// POST /api/scan/vulnerabilities -- scan and append to the chain.
  ///
  /// A 409 comes back as a body rather than an exception. The engine
  /// refuses to append onto a broken chain, and the reason it gives is
  /// the thing a reader needs; a status code alone would hide it.
  Future<Map<String, dynamic>> run({List<String>? trees}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/scan/vulnerabilities'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(trees == null ? {} : {'trees': trees}),
    );
    if (r.statusCode == 409) return _body(r);
    return _decode(r);
  }
}
