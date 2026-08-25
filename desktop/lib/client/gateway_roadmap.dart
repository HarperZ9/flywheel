// Typed PM-roadmap API: one read-only route, GET /api/pm/roadmap.
// The roadmap is assembled engine-side from sealed receipts on every
// request; nothing here writes or admits.
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'gateway_auth.dart';
import 'gateway_error.dart';

class RoadmapApi {
  final String baseUrl;
  final http.Client _http;

  RoadmapApi({String? baseUrl, http.Client? httpClient})
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

  /// GET /api/pm/roadmap -- goals with per-child verification status,
  /// a verification floor, and the page's own does-not-prove notes.
  Future<Map<String, dynamic>> roadmap() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/pm/roadmap'));
    return _decode(r);
  }
}
