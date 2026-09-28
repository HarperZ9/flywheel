enum EffectSourceKind { actionWitness, toolReceipts }

final class EffectSourceSummary {
  final String status;
  final int? count;
  final int? traceSequence;
  final String? kind, recordSha256, recordKind, payloadKind;
  final String? valueSha256, headSha256, jsonPointer, reason;

  const EffectSourceSummary._(
      this.status,
      this.count,
      this.traceSequence,
      this.kind,
      this.recordSha256,
      this.recordKind,
      this.payloadKind,
      this.valueSha256,
      this.headSha256,
      this.jsonPointer,
      this.reason);

  factory EffectSourceSummary.fromJson(Map<String, dynamic> value,
      EffectSourceKind kind, {required int recordCount}) {
    final status = value['status'];
    if (!const {'present', 'absent', 'omitted', 'unavailable'}
        .contains(status)) {
      _invalid();
    }
    final pointer = kind == EffectSourceKind.actionWitness
        ? '/payload/action_witness'
        : '/payload/tool_call_receipts';
    if (status != 'present') {
      return status == 'unavailable'
          ? _unavailable(value, pointer, recordCount)
          : _short(value, status as String);
    }
    final headField =
        kind == EffectSourceKind.actionWitness ? 'head_sha256' : 'chain_head_sha256';
    final summaryKind = kind == EffectSourceKind.actionWitness
        ? 'reported_action_witness_summary'
        : 'reported_tool_call_receipts_summary';
    _fields(value, {
      'status',
      'kind',
      'trace_sequence',
      'record_sha256',
      'record_kind',
      'payload_kind',
      'value_sha256',
      'count',
      headField,
      'json_pointer'
    });
    if (value['json_pointer'] != pointer ||
        value['kind'] != summaryKind ||
        value['record_kind'] != 'result' ||
        value['payload_kind'] != 'result') {
      _invalid();
    }
    return EffectSourceSummary._(
        status as String,
        _count(value['count']),
        _sequence(value['trace_sequence'], recordCount),
        summaryKind,
        _sha(value['record_sha256']),
        value['record_kind'] as String,
        value['payload_kind'] as String,
        _sha(value['value_sha256']),
        _sha(value[headField]),
        pointer,
        null);
  }
}

EffectSourceSummary _unavailable(
    Map<String, dynamic> value, String pointer, int recordCount) {
  _fields(value, {
    'status',
    'reason',
    'trace_sequence',
    'record_sha256',
    'record_kind',
    'json_pointer',
    if (value.containsKey('value_sha256')) 'value_sha256',
  });
  if (value['json_pointer'] != pointer ||
      !const {'UNSUPPORTED_SOURCE_RECORD_KIND', 'UNSUPPORTED_BLOCK_SHAPE'}
          .contains(value['reason'])) {
    _invalid();
  }
  return EffectSourceSummary._(
      value['status'] as String,
      null,
      _sequence(value['trace_sequence'], recordCount),
      null,
      _sha(value['record_sha256']),
      _recordKind(value['record_kind']),
      null,
      value.containsKey('value_sha256') ? _sha(value['value_sha256']) : null,
      null,
      pointer,
      value['reason'] as String);
}

EffectSourceSummary _short(Map<String, dynamic> value, String status) {
  _fields(value, const {'status'});
  return EffectSourceSummary._(
      status, null, null, null, null, null, null, null, null, null, null);
}

Never _invalid() =>
    throw const FormatException('Gateway effect source summary is invalid');

int _count(Object? value) {
  if (value is! int || value < 0) _invalid();
  return value;
}

int _sequence(Object? value, int recordCount) {
  if (value is! int || value < 0 || value >= recordCount) _invalid();
  return value;
}

String _sha(Object? value) {
  if (value is! String || !RegExp(r'^[0-9a-f]{64}$').hasMatch(value)) {
    _invalid();
  }
  return value;
}

String _recordKind(Object? value) {
  if (value is! String ||
      !const {'request', 'ledger', 'progress', 'result', 'failure'}
          .contains(value)) {
    _invalid();
  }
  return value;
}

void _fields(Map<String, dynamic> value, Set<String> fields) {
  if (value.length != fields.length || !value.keys.every(fields.contains)) {
    _invalid();
  }
}
