import 'dart:convert';
import 'package:crypto/crypto.dart';

import 'agent_trace.dart';
import 'agent_trace_json.dart';
import 'canonical_json.dart';

final class TraceRecord {
  final String ownerRef, journeyRef, operationRef, traceRef, kind;
  final String priorSha256, recordSha256, canonicalText;
  final int sequence, byteCount;
  final Map<String, dynamic> payload;

  const TraceRecord._(
      this.ownerRef,
      this.journeyRef,
      this.operationRef,
      this.traceRef,
      this.kind,
      this.priorSha256,
      this.recordSha256,
      this.canonicalText,
      this.sequence,
      this.byteCount,
      this.payload);
}

final class TracePage {
  final TraceRecord record;
  final int recordCount;
  final String traceHeadSha256;
  final int? nextSequence;
  final List<String> doesNotProve;

  const TracePage._(this.record, this.recordCount, this.traceHeadSha256,
      this.nextSequence, this.doesNotProve);

  factory TracePage.fromJson(
    Map<String, dynamic> value, {
    required String operationRef,
    required String journeyRef,
    required String traceRef,
    required int sequence,
  }) {
    traceFields(value, {
      'schema',
      'trace_ref',
      'operation_ref',
      'journey_ref',
      'record_count',
      'trace_head_sha256',
      'record',
      'record_canonical_base64',
      'next_sequence',
      'does_not_prove'
    });
    if (value['schema'] != 'flywheel.gateway-agent-trace-detail/v1' ||
        traceReference(value['operation_ref'], 'op') != operationRef ||
        traceReference(value['journey_ref'], 'jrn') != journeyRef ||
        traceReference(value['trace_ref'], 'agt') != traceRef ||
        sequence < 0 ||
        sequence >= traceMaxRecords) {
      invalidTrace();
    }
    final count = value['record_count'];
    if (count is! int || count <= sequence || count > traceMaxRecords) {
      invalidTrace();
    }
    final next = value['next_sequence'];
    if (next != (sequence + 1 < count ? sequence + 1 : null)) invalidTrace();
    final raw = value['record_canonical_base64'];
    if (raw is! String) invalidTrace();
    if (raw.length > ((traceMaxRecordBytes + 2) ~/ 3) * 4) {
      throw const TraceLimitException();
    }
    final bytes = base64Decode(raw);
    if (bytes.length > traceMaxRecordBytes) throw const TraceLimitException();
    // Retain and hash original bytes. Re-encoding decoded floats is not a witness.
    final original = traceJsonObject(bytes);
    final returned = value['record'];
    if (returned is! Map<String, dynamic>) invalidTrace();
    traceFields(returned, {
      'schema',
      'owner_ref',
      'journey_ref',
      'operation_ref',
      'trace_ref',
      'sequence',
      'kind',
      'prior_sha256',
      'payload',
      'record_sha256'
    });
    final digest = traceDigest(returned['record_sha256']);
    if (sha256.convert(bytes).toString() != digest) invalidTrace();
    final material = Map<String, dynamic>.from(returned)
      ..remove('record_sha256');
    if (!_sameJson(original, material)) invalidTrace();
    final owner = traceReference(original['owner_ref'], 'owner');
    final boundRef = 'agt_${canonicalJsonSha256({
          'owner_ref': owner,
          'journey_ref': journeyRef,
          'operation_ref': operationRef,
        }).substring(0, 32)}';
    if (original['schema'] != 'flywheel.gateway-agent-record/v1' ||
        original['operation_ref'] != operationRef ||
        original['journey_ref'] != journeyRef ||
        original['trace_ref'] != traceRef ||
        boundRef != traceRef ||
        original['sequence'] != sequence ||
        original['sequence'] is! int ||
        !const {
          'request',
          'ledger',
          'progress',
          'result',
          'failure',
        }.contains(original['kind']) ||
        original['payload'] is! Map<String, dynamic>) {
      invalidTrace();
    }
    final prior = traceDigest(original['prior_sha256']);
    if (sequence == 0 && prior != traceGenesis) invalidTrace();
    final record = TraceRecord._(
        owner,
        journeyRef,
        operationRef,
        traceRef,
        original['kind'] as String,
        prior,
        digest,
        utf8.decode(bytes),
        sequence,
        bytes.length,
        _freeze(original['payload']) as Map<String, dynamic>);
    return TracePage._(
        record,
        count,
        traceDigest(value['trace_head_sha256']),
        next as int?,
        traceCodes(value['does_not_prove'], const {
          'NOT_SEMANTIC_TRUTH',
          'NOT_UNLIMITED_TOOL_OUTPUT',
        }));
  }
}

bool _sameJson(Object? a, Object? b) {
  if (a is Map && b is Map) {
    return a.length == b.length &&
        a.keys.every((key) => b.containsKey(key) && _sameJson(a[key], b[key]));
  }
  if (a is List && b is List) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (!_sameJson(a[i], b[i])) return false;
    }
    return true;
  }
  if (a is double && b is double) {
    return a.isFinite && b.isFinite && a == b && a.isNegative == b.isNegative;
  }
  return a.runtimeType == b.runtimeType && a == b;
}

Object? _freeze(Object? value) {
  if (value is Map<String, dynamic>) {
    return Map<String, dynamic>.unmodifiable(
        value.map((key, item) => MapEntry(key, _freeze(item))));
  }
  if (value is List) return List<Object?>.unmodifiable(value.map(_freeze));
  return value;
}
