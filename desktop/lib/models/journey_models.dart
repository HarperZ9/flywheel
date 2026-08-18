import 'evidence_state.dart';
export 'evidence_state.dart';

final _journeyRef = RegExp(r'^jrn_[0-9a-f]{32}$');

enum JourneyStage {
  intake,
  decomposed,
  preflight,
  running,
  concluded,
  exported,
  invalidResponse
}

enum JourneyOperationState {
  unknown,
  queued,
  blocked,
  running,
  cancelRequested,
  completed,
  failed,
  cancelled,
  invalidResponse
}

JourneyStage _stage(Object? raw, String field, List<ParseIssue> issues) {
  for (final value in JourneyStage.values) {
    if (value != JourneyStage.invalidResponse && value.name == raw) {
      return value;
    }
  }
  addParseIssue(issues, field, raw);
  return JourneyStage.invalidResponse;
}

JourneyOperationState _operationState(
    Object? raw, String field, List<ParseIssue> issues) {
  final key = raw == 'cancel_requested' ? 'cancelRequested' : raw;
  for (final value in JourneyOperationState.values) {
    if (value != JourneyOperationState.invalidResponse && value.name == key) {
      return value;
    }
  }
  addParseIssue(issues, field, raw);
  return JourneyOperationState.invalidResponse;
}

JourneyLens? _lens(Object? raw, List<ParseIssue> issues) {
  if (raw == null) return null;
  const values = {
    'Rescue': JourneyLens.rescue,
    'Diagnose': JourneyLens.diagnose,
    'Verify': JourneyLens.verify,
  };
  final parsed = values[raw];
  if (parsed != null) return parsed;
  addParseIssue(issues, 'lens', raw);
  return JourneyLens.invalidResponse;
}

Map<String, EvidenceVerdict> _verdicts(
    Object? raw, Map<String, String> rawValues, List<ParseIssue> issues) {
  if (raw is! Map) {
    addParseIssue(issues, 'verdicts', raw);
    return const {};
  }
  for (final key in raw.keys) {
    if (key is! String || !isSafePublicText(key)) {
      addParseIssue(issues, 'verdicts.key', key);
      return const {};
    }
  }
  final parsed = <String, EvidenceVerdict>{};
  for (final entry in raw.entries) {
    final key = entry.key as String;
    rawValues[key] = safeRawValue(entry.value) ?? '';
    parsed[key] = parseEvidenceVerdict(entry.value, 'verdicts.$key', issues);
  }
  return Map.unmodifiable(parsed);
}

Map<String, String>? _conclusion(Object? raw, List<ParseIssue> issues) {
  if (raw == null) return null;
  if (raw is! Map ||
      raw.values.any((value) => value is! String || !isSafePublicText(value)) ||
      raw.keys.any((key) => key != 'summary' && key != 'does_not_prove')) {
    addParseIssue(issues, 'conclusion', raw);
    return null;
  }
  return Map<String, String>.unmodifiable(raw);
}

class JourneyNextAction extends DefensiveModel {
  final String actionId, kind, description;
  final List<String> basisRefs;
  JourneyNextAction._(this.actionId, this.kind, this.description,
      this.basisRefs, super.parseIssues);
  factory JourneyNextAction.fromJson(Map<String, Object?> json, String field) {
    final issues = <ParseIssue>[];
    return JourneyNextAction._(
        readText(json, 'action_id', issues),
        readText(json, 'kind', issues),
        readText(json, 'description', issues),
        readStringList(json['basis_refs'], '$field.basis_refs', issues),
        issues);
  }
}

class JourneyProjection extends DefensiveModel {
  final String journeyRef, eventHeadSha256, rawStage, detail;
  final List<String> factIds, claimIds;
  final List<JourneyCheck> checks;
  final Map<String, EvidenceVerdict> verdicts;
  final Map<String, String> rawVerdicts;
  final List<JourneyMissingEvidence> missingEvidence;
  final JourneyStage stage;
  final Map<String, String>? conclusion;
  final List<JourneyNextAction> nextActions;
  final JourneyLens? lens;
  JourneyProjection._(
      {required this.journeyRef,
      required this.eventHeadSha256,
      required this.factIds,
      required this.claimIds,
      required this.checks,
      required this.verdicts,
      required this.rawVerdicts,
      required this.missingEvidence,
      required this.stage,
      required this.rawStage,
      required this.conclusion,
      required this.nextActions,
      required this.detail,
      required this.lens,
      required List<ParseIssue> parseIssues})
      : super(parseIssues);
  factory JourneyProjection.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    expectSchema(json, 'flywheel.evidence-journey-projection/v2', issues);
    final rawVerdicts = <String, String>{};
    final checks =
        readRecords(json['checks'], 'checks', issues, JourneyCheck.fromJson);
    final missing = readRecords(
        json['missing_evidence'],
        'missing_evidence',
        issues,
        (json, field) => readJourneyMissingEvidence(json, field, issues));
    final actions = readRecords(json['next_actions'], 'next_actions', issues,
        JourneyNextAction.fromJson);
    issues.addAll(checks.expand((item) => item.parseIssues));
    issues.addAll(actions.expand((item) => item.parseIssues));
    return JourneyProjection._(
        journeyRef: readText(json, 'journey_ref', issues, pattern: _journeyRef),
        eventHeadSha256:
            readText(json, 'event_head_sha256', issues, pattern: sha256Pattern),
        factIds: readStringList(json['fact_ids'], 'fact_ids', issues),
        claimIds: readStringList(json['claim_ids'], 'claim_ids', issues),
        checks: checks,
        verdicts: _verdicts(json['verdicts'], rawVerdicts, issues),
        rawVerdicts: Map.unmodifiable(rawVerdicts),
        missingEvidence: missing,
        stage: _stage(json['stage'], 'stage', issues),
        rawStage: safeRawValue(json['stage']) ?? '',
        conclusion: _conclusion(json['conclusion'], issues),
        nextActions: actions,
        detail: readDetail(json, 'detail', issues),
        lens: _lens(json['lens'], issues),
        parseIssues: issues);
  }
  bool sameEvidenceAs(JourneyProjection other) =>
      !invalidResponse &&
      !other.invalidResponse &&
      eventHeadSha256 == other.eventHeadSha256 &&
      sameList(factIds, other.factIds, (a, b) => a == b) &&
      sameList(claimIds, other.claimIds, (a, b) => a == b) &&
      sameList(checks, other.checks, (a, b) => a.sameEvidenceAs(b)) &&
      sameStringMap(rawVerdicts, other.rawVerdicts) &&
      sameList(missingEvidence, other.missingEvidence, sameMissingEvidence) &&
      rawStage == other.rawStage &&
      sameOptionalMap(conclusion, other.conclusion);
}

typedef JourneySummary = JourneyProjection;

class JourneyListResult extends DefensiveModel {
  final List<JourneySummary> journeys;
  JourneyListResult._(this.journeys, super.parseIssues);
  factory JourneyListResult.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    expectSchema(json, 'flywheel.evidence-journey-list/v2', issues);
    final journeys = readRecords(json['journeys'], 'journeys', issues,
        (item, _) => JourneySummary.fromJson(item));
    issues.addAll(journeys.expand((item) => item.parseIssues));
    return JourneyListResult._(journeys, issues);
  }
}

class JourneyCancelResult extends DefensiveModel {
  final String operationRef, eventHeadSha256, terminalEventRef;
  final String? rawOperationState;
  final JourneyOperationState operationState;
  JourneyCancelResult._(
      this.operationRef,
      this.operationState,
      this.rawOperationState,
      this.eventHeadSha256,
      this.terminalEventRef,
      super.parseIssues);
  factory JourneyCancelResult.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    final rawState = json['state'];
    return JourneyCancelResult._(
        readText(json, 'operation_ref', issues, pattern: operationRefPattern),
        _operationState(rawState, 'state', issues),
        safeRawValue(rawState),
        readText(json, 'event_head_sha256', issues, pattern: sha256Pattern),
        readText(json, 'terminal_event_ref', issues, pattern: sha256Pattern),
        issues);
  }
}

class JourneyMutationAck extends DefensiveModel {
  final String journeyRef, eventHeadSha256, eventSha256, projectionSha256;
  final bool idempotentReplay;
  final String? operationRef, rawOperationState;
  final JourneyOperationState? operationState;
  JourneyMutationAck._(
      this.journeyRef,
      this.eventHeadSha256,
      this.eventSha256,
      this.projectionSha256,
      this.idempotentReplay,
      this.operationRef,
      this.operationState,
      this.rawOperationState,
      super.parseIssues);
  factory JourneyMutationAck.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    expectSchema(json, 'flywheel.evidence-journey-mutation-ack/v2', issues);
    final operation = readText(json, 'operation_ref', issues,
        optional: true, pattern: operationRefPattern);
    final rawState = json['state'];
    return JourneyMutationAck._(
        readText(json, 'journey_ref', issues, pattern: _journeyRef),
        readText(json, 'event_head_sha256', issues, pattern: sha256Pattern),
        readText(json, 'event_sha256', issues, pattern: sha256Pattern),
        readText(json, 'projection_sha256', issues, pattern: sha256Pattern),
        readValue<bool>(json, 'idempotent_replay', issues, false),
        operation.isEmpty ? null : operation,
        rawState == null ? null : _operationState(rawState, 'state', issues),
        safeRawValue(rawState),
        issues);
  }
}

class JourneyExportResult extends DefensiveModel {
  final (String, String, String, String, String, String) _refs;
  final (ReceiptState, ReceiptState, ReceiptState) _verdicts;
  final bool idempotentReplay;
  final List<String> doesNotProve;
  JourneyExportResult._(this._refs, this._verdicts, this.idempotentReplay,
      this.doesNotProve, super.parseIssues);
  String get journeyRef => _refs.$1;
  String get sourceEventHeadSha256 => _refs.$2;
  String get finalEventHeadSha256 => _refs.$3;
  String get finalProjectionSha256 => _refs.$4;
  String get packetRef => _refs.$5;
  String get packetDigest => _refs.$6;
  ReceiptState get structuralVerdict => _verdicts.$1;
  ReceiptState get authenticityVerdict => _verdicts.$2;
  ReceiptState get rehashResistanceVerdict => _verdicts.$3;
  factory JourneyExportResult.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    expectSchema(json, 'flywheel.evidence-journey-export/v2', issues);
    if (json['profile'] != 'flywheel.evidence-journey-custody/v2') {
      addParseIssue(issues, 'profile', json['profile']);
    }
    return JourneyExportResult._((
      readText(json, 'journey_ref', issues, pattern: _journeyRef),
      readText(json, 'source_event_head_sha256', issues,
          pattern: sha256Pattern),
      readText(json, 'final_event_head_sha256', issues, pattern: sha256Pattern),
      readText(json, 'final_projection_sha256', issues, pattern: sha256Pattern),
      readText(json, 'packet_ref', issues),
      readText(json, 'packet_digest', issues, pattern: sha256Pattern),
    ), (
      parseReceiptState(
          json['structural_verdict'], 'structural_verdict', issues),
      parseReceiptState(
          json['authenticity_verdict'], 'authenticity_verdict', issues),
      parseReceiptState(json['rehash_resistance_verdict'],
          'rehash_resistance_verdict', issues),
    ),
        readValue<bool>(json, 'idempotent_replay', issues, false),
        readStringList(json['does_not_prove'], 'does_not_prove', issues),
        issues);
  }
}
