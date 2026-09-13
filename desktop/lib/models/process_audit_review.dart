import 'dart:convert';

import 'json_pointer_locator.dart';
import 'process_audit_packet_upload.dart';
export 'process_audit_packet_upload.dart';

final _sha256 = RegExp(r'^[0-9a-f]{64}$');

class ProcessAuditReviewResult {
  static const schemaName = 'flywheel.incident-sim-process-audit-review/v1';
  final ProcessAuditSource? source;
  final ProcessAuditVerification verification;
  final ProcessAuditDeclaredAccess declaredAccess;
  final List<ProcessAuditSourcePointer> sourcePointers;
  final List<String> limitations;
  final String assessment, semanticVerification;
  final String? errorCode, errorMessage;

  const ProcessAuditReviewResult._({
    this.source,
    required this.verification,
    required this.declaredAccess,
    required this.sourcePointers,
    required this.limitations,
    this.assessment = '',
    this.semanticVerification = 'UNVERIFIABLE',
    this.errorCode,
    this.errorMessage,
  });

  const ProcessAuditReviewResult.error(String code, String message)
      : this._(
          errorCode: code,
          errorMessage: message,
          verification: const ProcessAuditVerification.empty(),
          declaredAccess: const ProcessAuditDeclaredAccess.unknown(),
          sourcePointers: const [],
          limitations: const [],
        );

  factory ProcessAuditReviewResult.fromJson(
    Map<String, Object?> json,
    ProcessAuditPacketUpload upload,
  ) {
    final error = _map(json['error']);
    if (error.isNotEmpty) {
      return ProcessAuditReviewResult.error(
        _text(error['code'], fallback: 'GATEWAY_ERROR'),
        _text(error['message'], fallback: 'Process-audit review failed.'),
      );
    }
    final source = ProcessAuditSource.tryFromJson(_map(json['source']));
    final assessment = _text(json['assessment']);
    final verification =
        ProcessAuditVerification.tryFromJson(_map(json['verification']));
    final expectedAssessment =
        _assessmentForPacketVerdict(verification?.verdict ?? '');
    if (json['schema'] != schemaName ||
        source == null ||
        source.sha256 != upload.sha256 ||
        source.byteLength != upload.byteLength ||
        expectedAssessment == null ||
        assessment != expectedAssessment) {
      return const ProcessAuditReviewResult.error(
        'INVALID_RESPONSE',
        'Gateway returned an incomplete process-audit review.',
      );
    }
    final pointers = [
      for (final item in _maps(json['source_pointers']))
        ProcessAuditSourcePointer.fromJson(item, upload),
    ];
    return ProcessAuditReviewResult._(
      source: source,
      assessment: assessment,
      semanticVerification: 'UNVERIFIABLE',
      verification: verification!,
      declaredAccess:
          ProcessAuditDeclaredAccess.fromJson(_map(json['declared_access'])),
      sourcePointers: List.unmodifiable(pointers),
      limitations: List.unmodifiable(_strings(json['does_not_prove'])),
    );
  }

  String get packetIntegrityLabel => 'Packet integrity ${verification.verdict}';

  String get packetIntegrityStatus =>
      verification.verdict == 'MATCH' ? 'verified' : 'drift';
}

class ProcessAuditSource {
  final String format, sha256;
  final int byteLength;
  const ProcessAuditSource._(this.format, this.sha256, this.byteLength);

  static ProcessAuditSource? tryFromJson(Map<String, Object?> json) {
    final format = _text(json['format']);
    final sha = _text(json['sha256']);
    final length = _int(json['byte_length']);
    if (format != 'incident-sim-process-audit-json' ||
        !_sha256.hasMatch(sha) ||
        length < 1 ||
        length > maxProcessAuditPacketBytes) {
      return null;
    }
    return ProcessAuditSource._(format, sha, length);
  }
}

class ProcessAuditVerification {
  final String verdict, accessVerdict, packetDigest, evaluationDigest;
  final String sourceValuesDigest, independenceDigest;
  const ProcessAuditVerification({
    required this.verdict,
    required this.accessVerdict,
    required this.packetDigest,
    required this.evaluationDigest,
    required this.sourceValuesDigest,
    required this.independenceDigest,
  });
  const ProcessAuditVerification.empty()
      : this(
          verdict: '',
          accessVerdict: 'unknown',
          packetDigest: 'unknown',
          evaluationDigest: 'unknown',
          sourceValuesDigest: 'unknown',
          independenceDigest: 'unknown',
        );
  static ProcessAuditVerification? tryFromJson(Map<String, Object?> json) {
    final verdict = _packetVerdict(json['verdict']);
    final packetDigest = _packetVerdict(json['packet_digest_verdict']);
    final accessVerdict =
        _componentVerdict(json['institutional_access_verdict']);
    final evaluationDigest =
        _componentVerdict(json['evaluation_digest_verdict']);
    final sourceValuesDigest =
        _componentVerdict(json['source_values_digest_verdict']);
    final independenceDigest =
        _componentVerdict(json['independence_digest_verdict']);
    if (verdict == null ||
        packetDigest == null ||
        verdict != packetDigest ||
        accessVerdict == null ||
        evaluationDigest == null ||
        sourceValuesDigest == null ||
        independenceDigest == null) {
      return null;
    }
    return ProcessAuditVerification(
      verdict: verdict,
      accessVerdict: accessVerdict,
      packetDigest: packetDigest,
      evaluationDigest: evaluationDigest,
      sourceValuesDigest: sourceValuesDigest,
      independenceDigest: independenceDigest,
    );
  }
}

class ProcessAuditDeclaredAccess {
  final String verdict, coverageAssessment, reportedCoverageAssessment;
  final List<String> limits;
  const ProcessAuditDeclaredAccess({
    required this.verdict,
    required this.coverageAssessment,
    required this.reportedCoverageAssessment,
    required this.limits,
  });
  const ProcessAuditDeclaredAccess.unknown()
      : this(
          verdict: 'unknown',
          coverageAssessment: 'unknown',
          reportedCoverageAssessment: '',
          limits: const [],
        );
  factory ProcessAuditDeclaredAccess.fromJson(Map<String, Object?> json) =>
      ProcessAuditDeclaredAccess(
        verdict: _text(json['verdict'], fallback: 'unknown'),
        coverageAssessment:
            _text(json['coverage_assessment'], fallback: 'unknown'),
        reportedCoverageAssessment: _text(json['reported_coverage_assessment']),
        limits: List.unmodifiable(_strings(json['limits'])),
      );
}

class ProcessAuditSourcePointer {
  final String pointer, sourceValueText;
  final JsonPointerLocation? location;
  const ProcessAuditSourcePointer({
    required this.pointer,
    required this.sourceValueText,
    this.location,
  });
  factory ProcessAuditSourcePointer.fromJson(
    Map<String, Object?> json,
    ProcessAuditPacketUpload upload,
  ) {
    final pointer = _text(json['json_pointer'] ?? json['pointer']);
    return ProcessAuditSourcePointer(
      pointer: pointer,
      sourceValueText: json.containsKey('source_value')
          ? _displayValue(json['source_value'])
          : '',
      location: upload.locationFor(pointer),
    );
  }
  String get preview => sourceValueText.length <= 96
      ? sourceValueText
      : '${sourceValueText.substring(0, 96)}...';
}

String? _assessmentForPacketVerdict(String verdict) {
  if (verdict == 'MATCH') return 'packet-local-match';
  if (verdict == 'DRIFT') return 'packet-local-drift';
  return null;
}

String? _packetVerdict(Object? value) {
  if (value == 'MATCH' || value == 'DRIFT') return value as String;
  return null;
}

String? _componentVerdict(Object? value) {
  const known = {'MATCH', 'DRIFT', 'NOT_ASSESSED', 'UNKNOWN', 'unknown'};
  return value is String && known.contains(value) ? value : null;
}

Map<String, Object?> _map(Object? value) =>
    value is Map ? Map<String, Object?>.from(value) : <String, Object?>{};

List<Map<String, Object?>> _maps(Object? value) => value is List
    ? [
        for (final item in value)
          if (item is Map) Map<String, Object?>.from(item)
      ]
    : const [];

List<String> _strings(Object? value) => value is List
    ? [
        for (final item in value)
          if (item != null) _displayValue(item)
      ]
    : const [];

String _text(Object? value, {String fallback = ''}) =>
    value is String && value.isNotEmpty ? value : fallback;

int _int(Object? value) => value is int ? value : 0;

String _displayValue(Object? value) {
  if (value == null) return 'null';
  if (value is String) return value;
  return jsonEncode(value);
}
