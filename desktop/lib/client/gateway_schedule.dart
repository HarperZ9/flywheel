// Typed schedule API: the unattended-run surface, three routes.
//
// GET /api/schedule reads every schedule with what it owes and whether
// its fire history still verifies. POST /api/schedule/define seals one.
// POST /api/schedule/tick evaluates what is owed and fires it.
//
// The tick is a pull rather than a daemon, so this client asks and the
// engine hands back the arithmetic it did. Nothing here decides when
// work runs; it reports what ran and what was passed over.
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'gateway_auth.dart';
import 'gateway_error.dart';

class ScheduleApi {
  final String baseUrl;
  final http.Client _http;

  ScheduleApi({String? baseUrl, http.Client? httpClient})
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

  /// GET /api/schedule -- every schedule, its owed occurrences, and the
  /// chain verdict on its fire history.
  Future<Map<String, dynamic>> roster() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/schedule'));
    return _decode(r);
  }

  /// POST /api/schedule/define -- seal a schedule and store it.
  ///
  /// `catchUp` states what happens to occurrences that came due while
  /// nothing was running: `all` replays them, `latest` runs the newest
  /// and names the rest, `drop` runs none and names all of them. The
  /// engine has no default, so this parameter has none either.
  Future<Map<String, dynamic>> define({
    required String scheduleId,
    required String event,
    required int everySeconds,
    required String startsAt,
    required String catchUp,
  }) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/schedule/define'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'schedule_id': scheduleId,
        'event': event,
        'every_seconds': everySeconds,
        'starts_at': startsAt,
        'catch_up': catchUp,
      }),
    );
    return _decode(r);
  }

  /// POST /api/schedule/tick -- fire what is owed, for one schedule or
  /// for all of them. A schedule whose fire chain is broken refuses in
  /// its own result row rather than failing the whole tick.
  Future<Map<String, dynamic>> tick({String scheduleId = ''}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/schedule/tick'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(scheduleId.isEmpty ? {} : {'schedule_id': scheduleId}),
    );
    return _decode(r);
  }
}
