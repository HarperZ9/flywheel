part of 'process_audit_review.dart';

class ProcessAuditVerification {
  final String verdict, packetLocalVerdict, accessVerdict, packetDigest;
  final String evaluationDigest;
  final String sourceValuesDigest, independenceDigest, actionChain;
  final String workReceipt, audit, auditSubject, receiptVerification;
  final String gatewayEffectVerdict;
  final List<ProcessAuditVerifiedField> verifiedFields;
  const ProcessAuditVerification({
    required this.verdict,
    required this.packetLocalVerdict,
    required this.accessVerdict,
    required this.packetDigest,
    required this.evaluationDigest,
    required this.sourceValuesDigest,
    required this.independenceDigest,
    required this.actionChain,
    required this.workReceipt,
    required this.audit,
    required this.auditSubject,
    required this.receiptVerification,
    required this.gatewayEffectVerdict,
    required this.verifiedFields,
  });
  const ProcessAuditVerification.empty()
      : this(
          verdict: '',
          packetLocalVerdict: '',
          accessVerdict: 'unknown',
          packetDigest: 'unknown',
          evaluationDigest: 'unknown',
          sourceValuesDigest: 'unknown',
          independenceDigest: 'unknown',
          actionChain: 'unknown',
          workReceipt: 'unknown',
          audit: 'unknown',
          auditSubject: 'unknown',
          receiptVerification: 'unknown',
          gatewayEffectVerdict: 'unknown',
          verifiedFields: const [],
        );
  static ProcessAuditVerification? tryFromJson(Map<String, Object?> json) {
    final verdict = _packetVerdict(json['verdict']);
    final packetLocalVerdict =
        _packetVerdict(json['packet_local_verdict']) ?? verdict;
    final accessVerdict = _accessVerdict(json['institutional_access_verdict']);
    final packetDigest = _packetVerdict(json['packet_digest_verdict']);
    final evaluationDigest = _packetVerdict(json['evaluation_digest_verdict']);
    final sourceValuesDigest =
        _packetVerdict(json['source_values_digest_verdict']);
    final independenceDigest =
        _packetVerdict(json['independence_digest_verdict']);
    final actionChain = _packetVerdict(json['action_chain_verdict']);
    final workReceipt = _packetVerdict(json['work_receipt_verdict']);
    final audit = _packetVerdict(json['audit_verdict']);
    final auditSubject = _packetVerdict(json['audit_subject_verdict']);
    final receiptVerification =
        _packetVerdict(json['receipt_verification_verdict']);
    final gatewayEffectVerdict = json.containsKey('gateway_effect_verdict')
        ? _gatewayEffectVerdict(json['gateway_effect_verdict'])
        : 'UNAVAILABLE';
    final verifiedFields = _verifiedFields(json['verified_fields']);
    final components = [
      accessVerdict,
      packetDigest,
      evaluationDigest,
      sourceValuesDigest,
      independenceDigest,
      actionChain,
      workReceipt,
      audit,
      auditSubject,
      receiptVerification,
    ];
    if (verdict == null ||
        packetLocalVerdict == null ||
        gatewayEffectVerdict == null ||
        components.any((item) => item == null)) {
      return null;
    }
    if (verdict == 'MATCH' &&
        (packetLocalVerdict == 'DRIFT' ||
            components.contains('DRIFT') ||
            verifiedFields.any((item) => item.verdict == 'DRIFT'))) {
      return null;
    }
    if (packetLocalVerdict == 'MATCH' &&
        (components.contains('DRIFT') ||
            verifiedFields.any((item) => item.verdict == 'DRIFT'))) {
      return null;
    }
    return ProcessAuditVerification(
      verdict: verdict,
      packetLocalVerdict: packetLocalVerdict,
      accessVerdict: accessVerdict!,
      packetDigest: packetDigest!,
      evaluationDigest: evaluationDigest!,
      sourceValuesDigest: sourceValuesDigest!,
      independenceDigest: independenceDigest!,
      actionChain: actionChain!,
      workReceipt: workReceipt!,
      audit: audit!,
      auditSubject: auditSubject!,
      receiptVerification: receiptVerification!,
      gatewayEffectVerdict: gatewayEffectVerdict,
      verifiedFields: List.unmodifiable(verifiedFields),
    );
  }

  List<ProcessAuditVerifiedField> get failedFields => [
        for (final field in verifiedFields)
          if (field.verdict == 'DRIFT') field,
      ];
}

class ProcessAuditVerifiedField {
  final String field, verdict, check;
  const ProcessAuditVerifiedField({
    required this.field,
    required this.verdict,
    required this.check,
  });
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
  static ProcessAuditDeclaredAccess? tryFromJson(
    Map<String, Object?> json,
    String expectedVerdict,
  ) {
    final verdict = _accessVerdict(json['verdict']);
    final fallbackCoverage =
        expectedVerdict == 'NOT_ASSESSED' ? 'not_assessed' : 'unknown';
    final coverageAssessment = _text(
      json['coverage_assessment'],
      fallback: fallbackCoverage,
    );
    if (verdict == null || verdict != expectedVerdict) return null;
    if (verdict == 'NOT_ASSESSED' && coverageAssessment != 'not_assessed') {
      return null;
    }
    if (verdict == 'DRIFT' && coverageAssessment == 'complete') return null;
    return ProcessAuditDeclaredAccess(
      verdict: verdict,
      coverageAssessment: coverageAssessment,
      reportedCoverageAssessment: _text(json['reported_coverage_assessment']),
      limits: List.unmodifiable(_strings(json['limits'])),
    );
  }
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

String? _gatewayEffectVerdict(Object? value) {
  if (value == 'MATCH' || value == 'DRIFT' || value == 'UNAVAILABLE') {
    return value as String;
  }
  return null;
}

String? _accessVerdict(Object? value) {
  const known = {'MATCH', 'DRIFT', 'NOT_ASSESSED'};
  return value is String && known.contains(value) ? value : null;
}

List<ProcessAuditVerifiedField> _verifiedFields(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item is Map && _accessVerdict(item['verdict']) != null)
        ProcessAuditVerifiedField(
          field: _text(item['field'], fallback: '/unknown'),
          verdict: _accessVerdict(item['verdict'])!,
          check: _text(item['check'], fallback: 'reported by gateway'),
        ),
  ];
}
