import 'evidence_state.dart';

const gatewayGrantSummarySchema = 'flywheel.gateway-grant-summary/v1';
const gatewayProposalSchema = 'flywheel.gateway-grant-proposal/v1';
const _proposalFields = {
  'schema',
  'proposal_ref',
  'planned_grant_ref',
  'action',
  'journey_ref',
  'expected_event_head',
  'client_request_id',
  'destination',
  'tool',
  'operation_sha256',
  'arguments_sha256',
  'scopes',
  'data_refs',
  'credential_refs',
  'expires_at',
  'summary'
};
final _journeyRef = RegExp(r'^jrn_[0-9a-f]{32}$');
final _credentialRef = RegExp(r'^cred_[0-9a-f]{32}$');
final _dataRef = RegExp(r'^data_[A-Za-z0-9._:-]{0,123}$');

final class GatewayDestination {
  final String kind, ref;
  const GatewayDestination(this.kind, this.ref);

  factory GatewayDestination.fromJson(
      Object? raw, List<ParseIssue> issues, String field) {
    if (raw is! Map<String, Object?> ||
        raw.length != 2 ||
        !raw.containsKey('kind') ||
        !raw.containsKey('ref')) {
      addParseIssue(issues, field, raw);
      return const GatewayDestination('', '');
    }
    return GatewayDestination(
        readText(raw, 'kind', issues), readText(raw, 'ref', issues));
  }

  Map<String, String> toJson() => {'kind': kind, 'ref': ref};

  @override
  bool operator ==(Object other) =>
      other is GatewayDestination && kind == other.kind && ref == other.ref;

  @override
  int get hashCode => Object.hash(kind, ref);
}

final class GatewayJourneyBinding {
  final String journeyRef, eventHead;
  const GatewayJourneyBinding(this.journeyRef, this.eventHead);
  @override
  bool operator ==(Object other) =>
      other is GatewayJourneyBinding &&
      journeyRef == other.journeyRef &&
      eventHead == other.eventHead;
  @override
  int get hashCode => Object.hash(journeyRef, eventHead);
}

final class GatewayGrantSummary extends DefensiveModel {
  final String action, journeyRef, eventHead, tool, operationSha256;
  final String argumentsSha256, effect, expiresAt;
  final GatewayDestination destination;
  final List<String> scopes, dataRefs, credentialRefs;

  GatewayGrantSummary._(
      this.action,
      this.journeyRef,
      this.eventHead,
      this.destination,
      this.tool,
      this.operationSha256,
      this.argumentsSha256,
      this.scopes,
      this.dataRefs,
      this.credentialRefs,
      this.effect,
      this.expiresAt,
      super.parseIssues);

  factory GatewayGrantSummary.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    exactGatewayFields(
        json,
        const {
          'schema',
          'action',
          'journey_ref',
          'expected_event_head',
          'destination',
          'tool',
          'operation_sha256',
          'arguments_sha256',
          'scopes',
          'data_refs',
          'credential_refs',
          'effect',
          'expires_at'
        },
        issues,
        'summary');
    expectSchema(json, gatewayGrantSummarySchema, issues);
    return GatewayGrantSummary._(
        readText(json, 'action', issues),
        readText(json, 'journey_ref', issues, pattern: _journeyRef),
        readText(json, 'expected_event_head', issues, pattern: sha256Pattern),
        GatewayDestination.fromJson(json['destination'], issues, 'destination'),
        readText(json, 'tool', issues),
        readText(json, 'operation_sha256', issues, pattern: sha256Pattern),
        readText(json, 'arguments_sha256', issues, pattern: sha256Pattern),
        readStringList(json['scopes'], 'scopes', issues),
        readGatewayDataRefs(json['data_refs'], issues),
        readGatewayCredentialRefs(json['credential_refs'], issues),
        readText(json, 'effect', issues),
        readText(json, 'expires_at', issues),
        issues);
  }
}

final class GatewayGrantProposal extends DefensiveModel {
  final String proposalRef, plannedGrantRef, action, journeyRef, eventHead;
  final String clientRequestId, tool, operationSha256, argumentsSha256;
  final String expiresAt;
  final GatewayDestination destination;
  final List<String> scopes, dataRefs, credentialRefs;
  final GatewayGrantSummary summary;
  GatewayGrantProposal._(
      this.proposalRef,
      this.plannedGrantRef,
      this.action,
      this.journeyRef,
      this.eventHead,
      this.clientRequestId,
      this.destination,
      this.tool,
      this.operationSha256,
      this.argumentsSha256,
      this.scopes,
      this.dataRefs,
      this.credentialRefs,
      this.expiresAt,
      this.summary,
      super.parseIssues);

  factory GatewayGrantProposal.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    exactGatewayFields(json, _proposalFields, issues, 'proposal');
    expectSchema(json, gatewayProposalSchema, issues);
    final summary = json['summary'] is Map<String, Object?>
        ? GatewayGrantSummary.fromJson(json['summary'] as Map<String, Object?>)
        : GatewayGrantSummary.fromJson(const {});
    issues.addAll(summary.parseIssues);
    final proposal =
        readText(json, 'proposal_ref', issues, pattern: proposalRefPattern);
    final grant =
        readText(json, 'planned_grant_ref', issues, pattern: grantRefPattern);
    final action = readText(json, 'action', issues);
    final journey = readText(json, 'journey_ref', issues, pattern: _journeyRef);
    final head =
        readText(json, 'expected_event_head', issues, pattern: sha256Pattern);
    final destination =
        GatewayDestination.fromJson(json['destination'], issues, 'destination');
    final tool = readText(json, 'tool', issues);
    final operation =
        readText(json, 'operation_sha256', issues, pattern: sha256Pattern);
    final arguments =
        readText(json, 'arguments_sha256', issues, pattern: sha256Pattern);
    final scopes = readStringList(json['scopes'], 'scopes', issues);
    final data = readGatewayDataRefs(json['data_refs'], issues);
    final credentials =
        readGatewayCredentialRefs(json['credential_refs'], issues);
    final expires = readText(json, 'expires_at', issues);
    if (proposal.length == 36 &&
        grant.length == 36 &&
        proposal.substring(4) != grant.substring(4)) {
      addParseIssue(issues, 'planned_grant_ref', grant);
    }
    if (!_summaryMatches(summary, action, journey, head, destination, tool,
        operation, arguments, scopes, data, credentials, expires)) {
      addParseIssue(issues, 'summary', null);
    }
    return GatewayGrantProposal._(
        proposal,
        grant,
        action,
        journey,
        head,
        readText(json, 'client_request_id', issues),
        destination,
        tool,
        operation,
        arguments,
        scopes,
        data,
        credentials,
        expires,
        summary,
        issues);
  }
}

List<String> readGatewayCredentialRefs(Object? raw, List<ParseIssue> issues) {
  final values = readStringList(raw, 'credential_refs', issues);
  if (values.any((value) => !_credentialRef.hasMatch(value)) ||
      values.toSet().length != values.length) {
    addParseIssue(issues, 'credential_refs', raw);
    return const [];
  }
  return values;
}

List<String> readGatewayDataRefs(Object? raw, List<ParseIssue> issues) {
  final values = readStringList(raw, 'data_refs', issues);
  if (values.any((value) => !_dataRef.hasMatch(value)) ||
      values.toSet().length != values.length) {
    addParseIssue(issues, 'data_refs', raw);
    return const [];
  }
  return values;
}

void exactGatewayFields(Map<String, Object?> value, Set<String> fields,
    List<ParseIssue> issues, String field) {
  if (value.keys.toSet().length != fields.length ||
      !value.keys.every(fields.contains)) {
    addParseIssue(issues, field, value.keys.toList());
  }
}

bool sameGatewayStringList(List<String> left, List<String> right) =>
    left.length == right.length &&
    left.indexed.every((item) => item.$2 == right[item.$1]);

bool sameGatewayValue(Object? left, Object? right) {
  if (left is Map && right is Map) {
    return left.length == right.length &&
        left.entries.every((entry) =>
            right.containsKey(entry.key) &&
            sameGatewayValue(entry.value, right[entry.key]));
  }
  if (left is List && right is List) {
    return left.length == right.length &&
        left.indexed
            .every((entry) => sameGatewayValue(entry.$2, right[entry.$1]));
  }
  return left == right;
}

int gatewayValueHash(Object? value) {
  if (value is Map) {
    final keys = value.keys.map((key) => key.toString()).toList()..sort();
    return Object.hashAll(
        keys.map((key) => Object.hash(key, gatewayValueHash(value[key]))));
  }
  if (value is List) return Object.hashAll(value.map(gatewayValueHash));
  return value.hashCode;
}

bool _summaryMatches(
        GatewayGrantSummary s,
        String action,
        String journey,
        String head,
        GatewayDestination destination,
        String tool,
        String operation,
        String arguments,
        List<String> scopes,
        List<String> data,
        List<String> credentials,
        String expires) =>
    s.action == action &&
    s.journeyRef == journey &&
    s.eventHead == head &&
    s.destination == destination &&
    s.tool == tool &&
    s.operationSha256 == operation &&
    s.argumentsSha256 == arguments &&
    s.expiresAt == expires &&
    sameGatewayStringList(s.scopes, scopes) &&
    sameGatewayStringList(s.dataRefs, data) &&
    sameGatewayStringList(s.credentialRefs, credentials);
