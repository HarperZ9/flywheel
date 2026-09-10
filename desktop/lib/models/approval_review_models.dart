import 'evidence_state.dart';
import 'gateway_grant_summary.dart';

const gatewayGrantReviewSchema = 'flywheel.gateway-grant-review/v1';
final _journeyRef = RegExp(r'^jrn_[0-9a-f]{32}$');
final _requestId = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$');
final _secretKey = RegExp(
    r'(?:^|[_-])(api[_-]?key|token|secret|password|credential)(?:$|[_-])',
    caseSensitive: false);

final class GatewayGrantReview extends DefensiveModel {
  final String proposalRef, plannedGrantRef, recordSha256, reviewSha256;
  final String operationRef, action, journeyRef, eventHead, clientRequestId;
  final GatewayDestination destination;
  final String tool, executionPlanSha256, operationSha256, argumentsSha256;
  final String expiresAt;
  final List<String> scopes, dataRefs, credentialRefs;
  final Map<String, Object?> operation;

  GatewayGrantReview._(
      this.proposalRef,
      this.plannedGrantRef,
      this.recordSha256,
      this.reviewSha256,
      this.operationRef,
      this.action,
      this.journeyRef,
      this.eventHead,
      this.clientRequestId,
      this.destination,
      this.tool,
      this.scopes,
      this.dataRefs,
      this.credentialRefs,
      this.executionPlanSha256,
      this.operationSha256,
      this.argumentsSha256,
      this.operation,
      this.expiresAt,
      super.parseIssues);

  Map<String, Object?> toExactJson() => {
        'schema': gatewayGrantReviewSchema,
        'proposal_ref': proposalRef,
        'planned_grant_ref': plannedGrantRef,
        'record_sha256': recordSha256,
        'review_sha256': reviewSha256,
        'operation_ref': operationRef,
        'action': action,
        'journey_ref': journeyRef,
        'expected_event_head': eventHead,
        'client_request_id': clientRequestId,
        'destination': destination.toJson(),
        'tool': tool,
        'scopes': scopes,
        'data_refs': dataRefs,
        'credential_refs': credentialRefs,
        'execution_plan_sha256': executionPlanSha256,
        'operation_sha256': operationSha256,
        'arguments_sha256': argumentsSha256,
        'operation': operation,
        'expires_at': expiresAt,
      };

  factory GatewayGrantReview.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    exactGatewayFields(
        json,
        const {
          'schema',
          'proposal_ref',
          'planned_grant_ref',
          'record_sha256',
          'review_sha256',
          'operation_ref',
          'action',
          'journey_ref',
          'expected_event_head',
          'client_request_id',
          'destination',
          'tool',
          'scopes',
          'data_refs',
          'credential_refs',
          'execution_plan_sha256',
          'operation_sha256',
          'arguments_sha256',
          'operation',
          'expires_at'
        },
        issues,
        'review');
    expectSchema(json, gatewayGrantReviewSchema, issues);
    final operation =
        freezeApprovalJson(json['operation'], issues, 'operation', [4096], 0);
    return GatewayGrantReview._(
        readText(json, 'proposal_ref', issues, pattern: proposalRefPattern),
        readText(json, 'planned_grant_ref', issues, pattern: grantRefPattern),
        readText(json, 'record_sha256', issues, pattern: sha256Pattern),
        readText(json, 'review_sha256', issues, pattern: sha256Pattern),
        readText(json, 'operation_ref', issues, pattern: operationRefPattern),
        readText(json, 'action', issues),
        readText(json, 'journey_ref', issues, pattern: _journeyRef),
        readText(json, 'expected_event_head', issues, pattern: sha256Pattern),
        readText(json, 'client_request_id', issues, pattern: _requestId),
        GatewayDestination.fromJson(json['destination'], issues, 'destination'),
        readText(json, 'tool', issues),
        readStringList(json['scopes'], 'scopes', issues),
        readGatewayDataRefs(json['data_refs'], issues),
        readGatewayCredentialRefs(json['credential_refs'], issues),
        readText(json, 'execution_plan_sha256', issues, pattern: sha256Pattern),
        readText(json, 'operation_sha256', issues, pattern: sha256Pattern),
        readText(json, 'arguments_sha256', issues, pattern: sha256Pattern),
        operation is Map<String, Object?> ? operation : const {},
        readText(json, 'expires_at', issues),
        issues);
  }
}

Object? freezeApprovalJson(Object? value, List<ParseIssue> issues, String field,
    List<int> budget, int depth,
    {String key = ''}) {
  if (depth > 16 || --budget[0] < 0) {
    addParseIssue(issues, field, null);
    return null;
  }
  if (value == null || value is bool || value is int) return value;
  if (value is num) {
    if (value.isFinite) return value;
    addParseIssue(issues, field, value);
    return null;
  }
  if (value is String) {
    if (isSafePublicText(value) ||
        (key == 'bulletin_base_url' && isCanonicalBulletinOrigin(value))) {
      return value;
    }
    addParseIssue(issues, field, value);
    return '';
  }
  if (value is List) {
    return List<Object?>.unmodifiable([
      for (final (index, item) in value.indexed)
        freezeApprovalJson(item, issues, '$field[$index]', budget, depth + 1,
            key: key)
    ]);
  }
  if (value is Map && value.keys.every((item) => item is String)) {
    final result = <String, Object?>{};
    for (final entry in value.entries) {
      final name = entry.key as String;
      if (_secretKey.hasMatch(name) && name != 'credential_refs') {
        addParseIssue(issues, '$field.$name', null);
        continue;
      }
      result[name] = freezeApprovalJson(
          entry.value, issues, '$field.$name', budget, depth + 1,
          key: name);
    }
    return Map<String, Object?>.unmodifiable(result);
  }
  addParseIssue(issues, field, value);
  return null;
}
