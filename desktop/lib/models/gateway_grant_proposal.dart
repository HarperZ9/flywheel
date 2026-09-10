part of 'gateway_grant_summary.dart';

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
  'summary',
};

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
    super.parseIssues,
  );

  factory GatewayGrantProposal.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    exactGatewayFields(json, _proposalFields, issues, 'proposal');
    expectSchema(json, gatewayProposalSchema, issues);
    final summary = json['summary'] is Map<String, Object?>
        ? GatewayGrantSummary.fromJson(json['summary'] as Map<String, Object?>)
        : GatewayGrantSummary.fromJson(const {});
    issues.addAll(summary.parseIssues);
    final proposal = readText(
      json,
      'proposal_ref',
      issues,
      pattern: proposalRefPattern,
    );
    final grant = readText(
      json,
      'planned_grant_ref',
      issues,
      pattern: grantRefPattern,
    );
    final action = readText(json, 'action', issues);
    final journey = readText(json, 'journey_ref', issues, pattern: _journeyRef);
    final head = readText(
      json,
      'expected_event_head',
      issues,
      pattern: sha256Pattern,
    );
    final destination = GatewayDestination.fromJson(
      json['destination'],
      issues,
      'destination',
    );
    final tool = readText(json, 'tool', issues);
    final operation = readText(
      json,
      'operation_sha256',
      issues,
      pattern: sha256Pattern,
    );
    final arguments = readText(
      json,
      'arguments_sha256',
      issues,
      pattern: sha256Pattern,
    );
    final scopes = readStringList(json['scopes'], 'scopes', issues);
    final data = readGatewayDataRefs(json['data_refs'], issues);
    final credentials = readGatewayCredentialRefs(
      json['credential_refs'],
      issues,
    );
    final expires = readText(json, 'expires_at', issues);
    if (proposal.length == 36 &&
        grant.length == 36 &&
        proposal.substring(4) != grant.substring(4)) {
      addParseIssue(issues, 'planned_grant_ref', grant);
    }
    if (!_summaryMatches(
      summary,
      action,
      journey,
      head,
      destination,
      tool,
      operation,
      arguments,
      scopes,
      data,
      credentials,
      expires,
    )) {
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
      issues,
    );
  }
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
  String expires,
) =>
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
