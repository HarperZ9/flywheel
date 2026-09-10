class ServiceDeskReviewResult {
  static const schemaName = 'flywheel.enterprise-env-review/v1';
  static const environmentId = 'service-desk-incident/v1';

  final ServiceDeskReview? review;
  final String? errorCode;
  final String? errorMessage;

  const ServiceDeskReviewResult._({
    this.review,
    this.errorCode,
    this.errorMessage,
  });

  factory ServiceDeskReviewResult.fromJson(Map<String, Object?> json) {
    final error = _map(json['error']);
    if (error.isNotEmpty) {
      return ServiceDeskReviewResult._(
        errorCode: _string(error['code'], fallback: 'GATEWAY_ERROR'),
        errorMessage: _string(
          error['message'],
          fallback: 'ServiceDesk review could not run.',
        ),
      );
    }
    if (json['schema'] != schemaName ||
        json['environment_id'] != environmentId) {
      return _upgradeRequired();
    }
    final report = _map(json['report']);
    final parsed = ServiceDeskReview.fromReport(
      report,
      artifactDirRef: _string(json['artifact_dir_ref']),
      artifactLabel: _string(json['artifact_label']),
    );
    if (parsed == null) return _upgradeRequired();
    return ServiceDeskReviewResult._(review: parsed);
  }

  static ServiceDeskReviewResult _upgradeRequired() =>
      const ServiceDeskReviewResult._(
        errorCode: 'PRODUCT_UPGRADE_REQUIRED',
        errorMessage:
            'The gateway returned an incomplete ServiceDesk review report. '
            'Install flywheel-env-service-desk-incident 0.2.0 or later from '
            'https://github.com/HarperZ9/flywheel/releases/tag/'
            'env-service-desk-incident-v0.2.0.',
      );
}

class ServiceDeskReview {
  static const reportSchema = 'service-desk-incident-env-review/v1';
  static const verificationSchema =
      'service-desk-incident-env-artifact-verification/v1';

  final String artifactDirRef;
  final String artifactLabel;
  final String observedState;
  final List<String> failureCodes;
  final bool claimedAllRecordedCasesPassed;
  final int? recordedCaseCount;
  final String claimedBasis;
  final String recomputedBasis;
  final String sourceIntegrityState;
  final String syntheticTaskState;
  final String recordConsistencyState;
  final String externalTrustState;
  final String externalTrustReason;
  final String syntheticAuthorization;
  final String syntheticLogOrigin;
  final List<String> limits;

  const ServiceDeskReview._({
    required this.artifactDirRef,
    required this.artifactLabel,
    required this.observedState,
    required this.failureCodes,
    required this.claimedAllRecordedCasesPassed,
    required this.recordedCaseCount,
    required this.claimedBasis,
    required this.recomputedBasis,
    required this.sourceIntegrityState,
    required this.syntheticTaskState,
    required this.recordConsistencyState,
    required this.externalTrustState,
    required this.externalTrustReason,
    required this.syntheticAuthorization,
    required this.syntheticLogOrigin,
    required this.limits,
  });

  static ServiceDeskReview? fromReport(
    Map<String, Object?> report, {
    required String artifactDirRef,
    required String artifactLabel,
  }) {
    final verification = _map(report['verification']);
    final claimed = _map(report['claimed_outcome']);
    final recomputed = _map(report['recomputed_outcome']);
    final layers = _map(report['evidence_layers']);
    final source = _map(layers['source_integrity']);
    final synthetic = _map(layers['synthetic_task_check']);
    final records = _map(layers['record_consistency']);
    final external = _map(layers['externally_trusted_evidence']);
    final limits = _strings(report['limits']);

    final complete = report['schema'] == reportSchema &&
        verification['schema'] == verificationSchema &&
        claimed.isNotEmpty &&
        recomputed.isNotEmpty &&
        source.isNotEmpty &&
        synthetic.isNotEmpty &&
        records.isNotEmpty &&
        external.isNotEmpty &&
        limits.isNotEmpty;
    if (!complete) return null;

    return ServiceDeskReview._(
      artifactDirRef: artifactDirRef,
      artifactLabel: _string(report['artifact_label'], fallback: artifactLabel),
      observedState: _string(
        verification['observed_state'],
        fallback: 'unknown',
      ),
      failureCodes: _strings(verification['failure_codes']),
      claimedAllRecordedCasesPassed:
          claimed['all_recorded_cases_passed'] == true,
      recordedCaseCount: claimed['recorded_case_count'] is int
          ? claimed['recorded_case_count'] as int
          : null,
      claimedBasis: _string(claimed['basis'], fallback: 'receipt claim'),
      recomputedBasis: _string(
        recomputed['basis'],
        fallback: 'recomputed review',
      ),
      sourceIntegrityState: _string(
        source['observed_state'],
        fallback: 'unknown',
      ),
      syntheticTaskState: _string(
        synthetic['observed_state'],
        fallback: 'unknown',
      ),
      recordConsistencyState: _string(
        records['observed_state'],
        fallback: 'unknown',
      ),
      externalTrustState: _string(
        external['observed_state'],
        fallback: 'unknown',
      ),
      externalTrustReason: _string(
        external['reason'],
        fallback: 'External trust was not established by this review.',
      ),
      syntheticAuthorization: _string(
        synthetic['authorization'],
        fallback: 'unchecked',
      ),
      syntheticLogOrigin: _string(
        synthetic['log_origin'],
        fallback: 'submitted_untrusted',
      ),
      limits: limits,
    );
  }

  String get displayState => observedState.toUpperCase();
}

String serviceDeskStatusForState(String state) => switch (state) {
      'pass' => 'verified',
      'fail' => 'drift',
      _ => 'unverifiable',
    };

Map<String, Object?> _map(Object? value) {
  if (value is Map) return Map<String, Object?>.from(value);
  return <String, Object?>{};
}

List<String> _strings(Object? value) {
  if (value is! List) return <String>[];
  return [
    for (final item in value)
      if (item is String) item,
  ];
}

String _string(Object? value, {String fallback = ''}) =>
    value is String && value.isNotEmpty ? value : fallback;
