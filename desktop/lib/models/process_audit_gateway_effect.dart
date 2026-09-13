part of 'process_audit_review.dart';

const _gatewayEffectOfflineSchema =
    'flywheel.gateway-effect-offline-verification/v1';
const _maxOfflineTraceRecords = 2048;

class GatewayEffectOfflineReview {
  final String verdict;
  final Map<String, String> sourceSha256;
  final GatewayEffectReviewBlock internalConsistency;
  final GatewayEffectExpectedCorrespondence expectedCorrespondence;
  final GatewayEffectCoverage effectCoverage;
  final GatewayEffectSemanticCorrectness semanticCorrectness;

  const GatewayEffectOfflineReview._({
    required this.verdict,
    required this.sourceSha256,
    required this.internalConsistency,
    required this.expectedCorrespondence,
    required this.effectCoverage,
    required this.semanticCorrectness,
  });

  static GatewayEffectOfflineReview? tryFromJson(Map<String, Object?> json) {
    try {
      if (!_only(json, {
        'schema',
        'verdict',
        if (json.containsKey('source_sha256')) 'source_sha256',
        'internal_consistency',
        'expected_correspondence',
        'effect_coverage',
        'semantic_correctness',
      })) {
        return null;
      }
      final verdict = _offlineVerdict(json['verdict']);
      final internal = GatewayEffectReviewBlock.tryFromJson(
          _map(json['internal_consistency']));
      final expected = GatewayEffectExpectedCorrespondence.tryFromJson(
          _map(json['expected_correspondence']));
      final coverage =
          GatewayEffectCoverage.tryFromJson(_map(json['effect_coverage']));
      final semantic = GatewayEffectSemanticCorrectness.tryFromJson(
          _map(json['semantic_correctness']));
      if (json['schema'] != _gatewayEffectOfflineSchema ||
          verdict == null ||
          internal == null ||
          expected == null ||
          coverage == null ||
          semantic == null) {
        return null;
      }
      final source = json.containsKey('source_sha256')
          ? _sourceSha256(_map(json['source_sha256']))
          : const <String, String>{};
      if (source == null) return null;
      return GatewayEffectOfflineReview._(
        verdict: verdict,
        sourceSha256: source,
        internalConsistency: internal,
        expectedCorrespondence: expected,
        effectCoverage: coverage,
        semanticCorrectness: semantic,
      );
    } on FormatException {
      return null;
    }
  }
}

class GatewayEffectReviewBlock {
  final String verdict;
  final List<GatewayEffectFieldCheck> checks;
  final List<String> limits;

  const GatewayEffectReviewBlock._(this.verdict, this.checks, this.limits);

  static GatewayEffectReviewBlock? tryFromJson(Map<String, Object?> json) {
    if (!_only(json, {
      'verdict',
      if (json.containsKey('checks')) 'checks',
      if (json.containsKey('limits')) 'limits',
    })) {
      return null;
    }
    final verdict = _offlineVerdict(json['verdict']);
    if (verdict == null) return null;
    final rawChecks = _optionalMapList(json['checks']);
    final checks = [
      for (final item in rawChecks)
        if (GatewayEffectFieldCheck.tryFromJson(item) != null)
          GatewayEffectFieldCheck.tryFromJson(item)!,
    ];
    if (rawChecks.length != checks.length) return null;
    return GatewayEffectReviewBlock._(
      verdict,
      List.unmodifiable(checks),
      List.unmodifiable(_stringList(json['limits'])),
    );
  }
}

class GatewayEffectFieldCheck {
  final String field, verdict, check;
  const GatewayEffectFieldCheck._(this.field, this.verdict, this.check);

  static GatewayEffectFieldCheck? tryFromJson(Map<String, Object?> json) {
    if (!_only(json, {'field', 'verdict', 'check'})) return null;
    final verdict = _matchDrift(json['verdict']);
    final field = _text(json['field']);
    final check = _text(json['check']);
    if (verdict == null || field.isEmpty || check.isEmpty) return null;
    return GatewayEffectFieldCheck._(field, verdict, check);
  }
}

class GatewayEffectExpectedCorrespondence {
  final String verdict, referenceProvenance;
  final List<GatewayEffectExpectedCheck> checks;
  final List<String> limits;

  const GatewayEffectExpectedCorrespondence._(
      this.verdict, this.referenceProvenance, this.checks, this.limits);

  static GatewayEffectExpectedCorrespondence? tryFromJson(
      Map<String, Object?> json) {
    if (!_only(json, {'verdict', 'reference_provenance', 'checks', 'limits'})) {
      return null;
    }
    final verdict = _offlineVerdict(json['verdict']);
    final rawChecks = _requiredMapList(json['checks']);
    final checks = [
      for (final item in rawChecks)
        if (GatewayEffectExpectedCheck.tryFromJson(item) != null)
          GatewayEffectExpectedCheck.tryFromJson(item)!,
    ];
    if (verdict == null || rawChecks.length != checks.length) {
      return null;
    }
    final provenance = json['reference_provenance'];
    if (provenance is! String || provenance.isEmpty) return null;
    return GatewayEffectExpectedCorrespondence._(
      verdict,
      provenance,
      List.unmodifiable(checks),
      List.unmodifiable(_stringList(json['limits'])),
    );
  }
}

class GatewayEffectExpectedCheck {
  final String artifact, expectedSha256, computedSha256, verdict;
  const GatewayEffectExpectedCheck._(
      this.artifact, this.expectedSha256, this.computedSha256, this.verdict);

  static GatewayEffectExpectedCheck? tryFromJson(Map<String, Object?> json) {
    if (!_only(
        json, {'artifact', 'expected_sha256', 'computed_sha256', 'verdict'})) {
      return null;
    }
    final artifact = _text(json['artifact']);
    final verdict = _matchDrift(json['verdict']);
    if (!const {'terminal_result', 'lifecycle_history', 'trace_records'}
            .contains(artifact) ||
        verdict == null) {
      return null;
    }
    return GatewayEffectExpectedCheck._(
      artifact,
      _sha(json['expected_sha256']),
      _sha(json['computed_sha256']),
      verdict,
    );
  }
}

class GatewayEffectSemanticCorrectness {
  final String verdict;
  final List<String> doesNotVerify;
  const GatewayEffectSemanticCorrectness._(this.verdict, this.doesNotVerify);

  static GatewayEffectSemanticCorrectness? tryFromJson(
      Map<String, Object?> json) {
    if (!_only(json, {'verdict', 'does_not_verify'}) ||
        json['verdict'] != 'UNVERIFIABLE') {
      return null;
    }
    final limits = _stringList(json['does_not_verify']);
    if (limits.isEmpty) return null;
    return GatewayEffectSemanticCorrectness._(
      'UNVERIFIABLE',
      List.unmodifiable(limits),
    );
  }
}

Map<String, String>? _sourceSha256(Map<String, Object?> json) {
  if (!_only(json, {'terminal_result', 'lifecycle_history', 'trace_records'})) {
    return null;
  }
  return Map.unmodifiable({
    'terminal_result': _sha(json['terminal_result']),
    'lifecycle_history': _sha(json['lifecycle_history']),
    'trace_records': _sha(json['trace_records']),
  });
}

int _boundedCount(Object? value) =>
    value is int && value >= 0 && value <= _maxOfflineTraceRecords ? value : -1;

String? _offlineVerdict(Object? value) =>
    value == 'MATCH' || value == 'DRIFT' || value == 'UNAVAILABLE'
        ? value as String
        : null;

String? _matchDrift(Object? value) =>
    value == 'MATCH' || value == 'DRIFT' ? value as String : null;

String _sha(Object? value) {
  if (value is String && _sha256.hasMatch(value)) return value;
  throw const FormatException('Gateway effect offline review is invalid');
}

bool _only(Map<String, Object?> value, Set<String> fields) =>
    value.length == fields.length && value.keys.every(fields.contains);

List<String> _stringList(Object? value) {
  if (value == null) return const [];
  if (value is! List || value.any((item) => item is! String)) {
    throw const FormatException('Gateway effect offline review is invalid');
  }
  return List<String>.unmodifiable(value.cast<String>());
}

List<Map<String, Object?>> _optionalMapList(Object? value) =>
    value == null ? const [] : _requiredMapList(value);

List<Map<String, Object?>> _requiredMapList(Object? value) {
  if (value is! List || value.any((item) => item is! Map)) {
    throw const FormatException('Gateway effect offline review is invalid');
  }
  return [
    for (final item in value) Map<String, Object?>.from(item as Map),
  ];
}
