part of 'process_audit_review.dart';

class GatewayEffectCoverage {
  final String verdict;
  final int retainedObservations, omittedObservations;
  final String knownObservationsDigest, traceHeadSha256;
  final List<GatewayEffectObservation> knownObservations;
  final GatewayEffectSourceStatus actionWitness, toolCallReceipts;
  final List<String> unobservedScope, limits;

  const GatewayEffectCoverage._({
    required this.verdict,
    required this.retainedObservations,
    required this.omittedObservations,
    required this.knownObservationsDigest,
    required this.traceHeadSha256,
    required this.knownObservations,
    required this.actionWitness,
    required this.toolCallReceipts,
    required this.unobservedScope,
    required this.limits,
  });

  static GatewayEffectCoverage? tryFromJson(Map<String, Object?> json) {
    final verdict = _offlineVerdict(json['verdict']);
    if (verdict == null) return null;
    if (verdict != 'MATCH') return _unavailable(verdict, json);
    if (!_only(json, {
      'verdict',
      'retained_observations',
      'omitted_observations',
      'known_observations_digest',
      'known_observations',
      'action_witness',
      'tool_call_receipts',
      'unobserved_scope',
      'trace_head_sha256',
    })) {
      return null;
    }
    final retained = _boundedCount(json['retained_observations']);
    final omitted = _boundedCount(json['omitted_observations']);
    final rawObservations = _requiredMapList(json['known_observations']);
    if (rawObservations.length != (retained < 64 ? retained : 64) ||
        omitted != retained - rawObservations.length) {
      return null;
    }
    final observations = _observations(rawObservations);
    final actionWitness =
        GatewayEffectSourceStatus.tryFromJson(_map(json['action_witness']));
    final receipts =
        GatewayEffectSourceStatus.tryFromJson(_map(json['tool_call_receipts']));
    if (observations == null || actionWitness == null || receipts == null) {
      return null;
    }
    return GatewayEffectCoverage._(
      verdict: verdict,
      retainedObservations: retained,
      omittedObservations: omitted,
      knownObservationsDigest: _sha(json['known_observations_digest']),
      traceHeadSha256: _sha(json['trace_head_sha256']),
      knownObservations: List.unmodifiable(observations),
      actionWitness: actionWitness,
      toolCallReceipts: receipts,
      unobservedScope: List.unmodifiable(_stringList(json['unobserved_scope'])),
      limits: const [],
    );
  }

  static GatewayEffectCoverage? _unavailable(
      String verdict, Map<String, Object?> json) {
    if (!_only(json, {'verdict', 'limits'})) return null;
    return GatewayEffectCoverage._(
      verdict: verdict,
      retainedObservations: 0,
      omittedObservations: 0,
      knownObservationsDigest: '',
      traceHeadSha256: '',
      knownObservations: const [],
      actionWitness: const GatewayEffectSourceStatus._('unavailable'),
      toolCallReceipts: const GatewayEffectSourceStatus._('unavailable'),
      unobservedScope: const [],
      limits: List.unmodifiable(_stringList(json['limits'])),
    );
  }

  static List<GatewayEffectObservation>? _observations(
      List<Map<String, Object?>> raw) {
    final observations = [
      for (final item in raw)
        if (GatewayEffectObservation.tryFromJson(item) != null)
          GatewayEffectObservation.tryFromJson(item)!,
    ];
    if (observations.length != raw.length) return null;
    for (var i = 1; i < observations.length; i++) {
      if (observations[i - 1].traceSequence >= observations[i].traceSequence) {
        return null;
      }
    }
    return observations;
  }
}

class GatewayEffectObservation {
  final int traceSequence;
  final String recordSha256, recordKind, jsonPointer, valueSha256;

  const GatewayEffectObservation._(this.traceSequence, this.recordSha256,
      this.recordKind, this.jsonPointer, this.valueSha256);

  static GatewayEffectObservation? tryFromJson(Map<String, Object?> json) {
    if (!_only(json, {
      'kind',
      'trace_sequence',
      'record_sha256',
      'record_kind',
      'payload_kind',
      'json_pointer',
      'value_sha256',
    })) {
      return null;
    }
    final sequence = json['trace_sequence'];
    if (json['kind'] != 'tool_result_edit_fingerprint' ||
        json['record_kind'] != 'ledger' ||
        json['payload_kind'] != 'tool_result' ||
        json['json_pointer'] != '/payload/meta/edited' ||
        sequence is! int ||
        sequence < 0 ||
        sequence >= _maxOfflineTraceRecords) {
      return null;
    }
    return GatewayEffectObservation._(
      sequence,
      _sha(json['record_sha256']),
      json['record_kind'] as String,
      json['json_pointer'] as String,
      _sha(json['value_sha256']),
    );
  }
}

class GatewayEffectSourceStatus {
  final String status;
  const GatewayEffectSourceStatus._(this.status);

  static GatewayEffectSourceStatus? tryFromJson(Map<String, Object?> json) {
    if (!_only(json, {'status'})) return null;
    final status = _text(json['status']);
    if (!const {'present', 'absent', 'omitted', 'unavailable'}
        .contains(status)) {
      return null;
    }
    return GatewayEffectSourceStatus._(status);
  }
}
