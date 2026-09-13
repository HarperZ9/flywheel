import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart' as crypto;

import 'inspect_evidence_upload.dart' show inspectDisplayFilename;
import 'json_pointer_locator.dart';

const int maxProcessAuditPacketBytes = 1024 * 1024;
const String processAuditPacketSchema =
    'flywheel.incident-sim-process-audit/v1';

final _sha256 = RegExp(r'^[0-9a-f]{64}$');

class ProcessAuditReviewException implements Exception {
  final String code, message;
  const ProcessAuditReviewException(this.code, this.message);
}

class ProcessAuditPacketUpload {
  final Uint8List bytes;
  final String sha256, detectedFormat;
  final int byteLength;
  final String? filename;
  final Map<String, JsonPointerLocation> _locations;

  ProcessAuditPacketUpload._({
    required this.bytes,
    required this.sha256,
    required this.byteLength,
    required this.filename,
    required this.detectedFormat,
    required Map<String, JsonPointerLocation> locations,
  }) : _locations = locations;

  factory ProcessAuditPacketUpload.fromPickedBytes(
    Uint8List picked, {
    String? filename,
  }) {
    final selected = _innerPacketBytes(picked);
    if (selected.bytes.isEmpty) {
      throw const ProcessAuditReviewException(
        'INVALID_LENGTH',
        'Process-audit JSON must not be empty.',
      );
    }
    if (selected.bytes.length > maxProcessAuditPacketBytes) {
      throw const ProcessAuditReviewException(
        'PAYLOAD_TOO_LARGE',
        'Process-audit packet bytes are over 1 MiB.',
      );
    }
    final bytes = Uint8List.fromList(selected.bytes);
    return ProcessAuditPacketUpload._(
      bytes: bytes,
      sha256: crypto.sha256.convert(bytes).toString(),
      byteLength: bytes.length,
      filename: inspectDisplayFilename(filename),
      detectedFormat: selected.format,
      locations: locateJsonPointers(bytes),
    );
  }

  JsonPointerLocation? locationFor(String pointer) => _locations[pointer];

  String get preview {
    try {
      return utf8.decode(bytes);
    } on Object {
      return 'Raw bytes are not valid UTF-8.';
    }
  }
}

({List<int> bytes, String format}) _innerPacketBytes(Uint8List picked) {
  try {
    final decoded = jsonDecode(utf8.decode(picked));
    if (decoded is Map && decoded['schema'] == processAuditPacketSchema) {
      return (bytes: picked, format: 'process-audit-packet');
    }
    final auditPacket = decoded is Map ? decoded['audit_packet'] : null;
    if (auditPacket is Map &&
        auditPacket['schema'] == processAuditPacketSchema) {
      return (bytes: utf8.encode(jsonEncode(auditPacket)), format: 'outer-command-report');
    }
  } on Object {
    // Send malformed selections unchanged so the gateway returns INVALID_JSON.
  }
  return (bytes: picked, format: 'selected-json');
}

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
    if (json['schema'] != schemaName ||
        source == null ||
        source.sha256 != upload.sha256 ||
        source.byteLength != upload.byteLength ||
        assessment.isEmpty) {
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
      verification: ProcessAuditVerification.fromJson(_map(json['verification'])),
      declaredAccess:
          ProcessAuditDeclaredAccess.fromJson(_map(json['declared_access'])),
      sourcePointers: List.unmodifiable(pointers),
      limitations: List.unmodifiable(_strings(json['does_not_prove'])),
    );
  }

  String get packetIntegrityLabel =>
      'Packet integrity ${verification.verdict.isEmpty ? assessment : verification.verdict}';

  String get packetIntegrityStatus =>
      assessment == 'packet-local-match' ? 'verified' : 'drift';
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
  factory ProcessAuditVerification.fromJson(Map<String, Object?> json) =>
      ProcessAuditVerification(
        verdict: _text(json['verdict'], fallback: 'unknown'),
        accessVerdict:
            _text(json['institutional_access_verdict'], fallback: 'unknown'),
        packetDigest: _text(json['packet_digest_verdict'], fallback: 'unknown'),
        evaluationDigest:
            _text(json['evaluation_digest_verdict'], fallback: 'unknown'),
        sourceValuesDigest:
            _text(json['source_values_digest_verdict'], fallback: 'unknown'),
        independenceDigest:
            _text(json['independence_digest_verdict'], fallback: 'unknown'),
      );
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
        reportedCoverageAssessment:
            _text(json['reported_coverage_assessment']),
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
  String get preview =>
      sourceValueText.length <= 96 ? sourceValueText : '${sourceValueText.substring(0, 96)}...';
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
    ? [for (final item in value) if (item != null) _displayValue(item)]
    : const [];

String _text(Object? value, {String fallback = ''}) =>
    value is String && value.isNotEmpty ? value : fallback;

int _int(Object? value) => value is int ? value : 0;

String _displayValue(Object? value) {
  if (value == null) return 'null';
  if (value is String) return value;
  return jsonEncode(value);
}
