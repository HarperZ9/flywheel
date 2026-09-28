import 'dart:convert';

import 'json_pointer_locator.dart';
import 'process_audit_packet_upload.dart';
export 'process_audit_packet_upload.dart';

part 'process_audit_verification.dart';
part 'process_audit_gateway_effect.dart';
part 'process_audit_gateway_effect_coverage.dart';

final _sha256 = RegExp(r'^[0-9a-f]{64}$');

class ProcessAuditReviewResult {
  static const schemaName = 'flywheel.incident-sim-process-audit-review/v1';
  final ProcessAuditSource? source;
  final ProcessAuditVerification verification;
  final ProcessAuditDeclaredAccess declaredAccess;
  final GatewayEffectOfflineReview? gatewayEffect;
  final List<ProcessAuditSourcePointer> sourcePointers;
  final List<String> limitations;
  final String assessment, semanticVerification;
  final String? errorCode, errorMessage;

  const ProcessAuditReviewResult._({
    this.source,
    required this.verification,
    required this.declaredAccess,
    this.gatewayEffect,
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
        _assessmentForPacketVerdict(verification?.packetLocalVerdict ?? '');
    final gatewayEffect = json.containsKey('gateway_effect_verification')
        ? GatewayEffectOfflineReview.tryFromJson(
            _map(json['gateway_effect_verification']))
        : null;
    final declaredAccess = ProcessAuditDeclaredAccess.tryFromJson(
      _map(json['declared_access']),
      verification?.accessVerdict ?? '',
    );
    if (json['schema'] != schemaName ||
        source == null ||
        source.sha256 != upload.sha256 ||
        source.byteLength != upload.byteLength ||
        expectedAssessment == null ||
        assessment != expectedAssessment ||
        (json.containsKey('gateway_effect_verification') &&
            gatewayEffect == null) ||
        !_gatewayConsistent(verification, gatewayEffect) ||
        declaredAccess == null) {
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
      declaredAccess: declaredAccess,
      gatewayEffect: gatewayEffect,
      sourcePointers: List.unmodifiable(pointers),
      limitations: List.unmodifiable(_strings(json['does_not_prove'])),
    );
  }

  String get packetIntegrityLabel =>
      'Packet integrity ${verification.packetLocalVerdict}';

  String get packetIntegrityStatus =>
      verification.packetLocalVerdict == 'MATCH' ? 'verified' : 'drift';
}

bool _gatewayConsistent(
  ProcessAuditVerification? verification,
  GatewayEffectOfflineReview? gatewayEffect,
) {
  if (verification == null || gatewayEffect == null) return true;
  final internal = gatewayEffect.internalConsistency.verdict;
  final expected = gatewayEffect.expectedCorrespondence.verdict;
  final calculatedGateway =
      internal == 'DRIFT' || expected == 'DRIFT' ? 'DRIFT' : internal;
  if (verification.gatewayEffectVerdict != internal) return false;
  if (verification.packetLocalVerdict == 'MATCH' && internal == 'DRIFT') {
    return false;
  }
  if (verification.verdict == 'MATCH' &&
      (verification.packetLocalVerdict == 'DRIFT' || expected == 'DRIFT')) {
    return false;
  }
  return gatewayEffect.verdict == calculatedGateway;
}

class ProcessAuditSource {
  final String format, sha256;
  final int byteLength;
  const ProcessAuditSource._(this.format, this.sha256, this.byteLength);

  static ProcessAuditSource? tryFromJson(Map<String, Object?> json) {
    final format = _text(json['format']);
    final sha = _text(json['sha256']);
    final length = _int(json['byte_length']);
    if (!const {
          'incident-sim-process-audit-json',
          'incident-sim-process-audit-review-request-json',
        }.contains(format) ||
        !_sha256.hasMatch(sha) ||
        length < 1 ||
        length > maxProcessAuditPacketBytes) {
      return null;
    }
    return ProcessAuditSource._(format, sha, length);
  }
}

class ProcessAuditSourcePointer {
  final String pointer, sourcePointer, source, privacy, sourceValueText;
  final List<String> limits;
  final JsonPointerLocation? location;
  const ProcessAuditSourcePointer({
    required this.pointer,
    required this.sourcePointer,
    required this.source,
    required this.privacy,
    required this.sourceValueText,
    required this.limits,
    this.location,
  });
  factory ProcessAuditSourcePointer.fromJson(
    Map<String, Object?> json,
    ProcessAuditPacketUpload upload,
  ) {
    final pointer = _text(json['json_pointer'] ?? json['pointer']);
    final source = _text(json['source']);
    final sourcePointer = _sourcePointer(pointer, source);
    return ProcessAuditSourcePointer(
      pointer: pointer,
      sourcePointer: sourcePointer,
      source: source,
      privacy: _text(json['privacy']),
      sourceValueText: json.containsKey('source_value')
          ? _displayValue(json['source_value'])
          : '',
      limits: List.unmodifiable(_strings(json['limits'])),
      location: upload.locationFor(sourcePointer),
    );
  }
  bool get isDerived => source == 'derived_from_submitted_trace_records';
  String get preview => sourceValueText.length <= 96
      ? sourceValueText
      : '${sourceValueText.substring(0, 96)}...';
}

String _sourcePointer(String pointer, String source) =>
    source == 'derived_from_submitted_trace_records' &&
            pointer == '/gateway_effect/trace_preview'
        ? '/gateway_effect/trace_records'
        : pointer;

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
