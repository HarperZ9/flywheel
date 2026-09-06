// Typed runner-pool API: the machines the operator owns, and the work
// they hold.
//
// GET /api/runners reads the pool as of now. Leases lapse against the
// clock rather than against a sweep somebody has to run, so two reads a
// minute apart can differ with nothing having been written between them.
//
// Only two of the six write verbs are here, and the omission is the
// point. Enrolling, claiming and completing are a machine's own acts; a
// console that performed them would be reporting on a pool it had
// joined. Minting a ticket and retiring a machine are the operator's,
// and those are the two this client can do.
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'gateway_auth.dart';
import 'gateway_error.dart';

class RunnersApi {
  final String baseUrl;
  final http.Client _http;

  RunnersApi({String? baseUrl, http.Client? httpClient})
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

  /// A 409 comes back as a body rather than an exception. The engine
  /// refuses to append onto a history that stopped verifying, and the
  /// sentence it gives is what a reader needs; a status code alone would
  /// leave the pool looking merely unavailable.
  Future<Map<String, dynamic>> _post(String path, Object body) async {
    final r = await _http.post(
      Uri.parse('$baseUrl$path'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    if (r.statusCode == 409) return _body(r);
    return _decode(r);
  }

  /// GET /api/runners -- machines, queued and leased work, lapsed leases,
  /// unspent tickets, and the chain verdict over all of it.
  Future<Map<String, dynamic>> roster() async {
    final r = await _http.get(Uri.parse('$baseUrl/api/runners'));
    return _decode(r);
  }

  /// POST /api/runners/tickets -- write one enrolment ticket.
  ///
  /// This route sits under private custody, so it carries the owner's
  /// bearer token where the machines' own routes do not. The labels
  /// granted here bound what the machine that spends it may advertise.
  Future<Map<String, dynamic>> mintTicket({
    required String ticketId,
    required List<String> labels,
  }) =>
      _post('/api/runners/tickets',
          {'ticket_id': ticketId, 'labels': labels});

  /// POST /api/runners/retire -- drop a machine from the pool.
  ///
  /// The record stays on the chain. Retiring ends the membership and
  /// does not erase that the machine was once in the pool, which is the
  /// half a reader auditing an old run needs.
  Future<Map<String, dynamic>> retire({required String runnerId}) =>
      _post('/api/runners/retire', {'runner_id': runnerId});
}
