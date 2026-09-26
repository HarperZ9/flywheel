// gateway_handoff.dart -- read one finished Rowan run as a handoff brief.
//
// GET /api/operations/{ref}/handoff returns a provider-neutral Markdown brief
// the engine renders from the run's private trace (harness/rowan_handoff.py):
// goal, where the run ended, deliverables with their verified / claimed /
// failed marks, open items and receipts. The desktop only carries it to the
// clipboard; it renders nothing itself.
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'gateway_auth.dart';
import 'gateway_error.dart';

const rowanHandoffSchema = 'flywheel.rowan-handoff/v1';
const _maxBriefBytes = 1024 * 1024;
final _operationRef = RegExp(r'^op_[0-9a-f]{32}$');
final _sha = RegExp(r'^[0-9a-f]{64}$');

final class RowanHandoff {
  final String operationRef, traceHeadSha256, markdown;
  final int recordCount;

  const RowanHandoff._(
      this.operationRef, this.traceHeadSha256, this.recordCount, this.markdown);

  factory RowanHandoff.fromJson(Object? raw, {required String operationRef}) {
    if (raw is! Map<String, dynamic> ||
        raw['schema'] != rowanHandoffSchema ||
        raw['operation_ref'] != operationRef ||
        raw['markdown'] is! String ||
        raw['record_count'] is! int ||
        raw['trace_head_sha256'] is! String ||
        !_sha.hasMatch(raw['trace_head_sha256'] as String)) {
      throw const FormatException('Handoff brief is invalid');
    }
    return RowanHandoff._(operationRef, raw['trace_head_sha256'] as String,
        raw['record_count'] as int, raw['markdown'] as String);
  }
}

class HandoffApi {
  final String baseUrl;
  final http.Client _http;

  HandoffApi({String? baseUrl, http.Client? httpClient})
      : baseUrl = baseUrl ?? 'http://127.0.0.1:8799',
        _http = httpClient ?? AuthedClient(http.Client());

  Future<RowanHandoff> read(String operationRef) async {
    if (!_operationRef.hasMatch(operationRef)) {
      throw ArgumentError('invalid operation reference');
    }
    final r = await _http
        .get(Uri.parse('$baseUrl/api/operations/$operationRef/handoff'));
    final text = utf8.decode(r.bodyBytes);
    if (r.statusCode >= 400) {
      throw GatewayException.fromResponse(r.statusCode, text);
    }
    if (r.bodyBytes.length > _maxBriefBytes) {
      throw const FormatException('Handoff brief is too large');
    }
    return RowanHandoff.fromJson(jsonDecode(text), operationRef: operationRef);
  }
}
