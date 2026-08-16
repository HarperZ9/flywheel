import 'evidence_state.dart';

const gatewayOperationSchema = 'flywheel.gateway-operation/v1';
const gatewayProposalSchema = 'flywheel.gateway-grant-proposal/v1';
const _proposalFields = {
  'schema',
  'proposal_ref',
  'planned_grant_ref',
  'action',
  'journey_ref',
  'expected_event_head',
  'client_request_id',
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
final _secretKey = RegExp(
    r'(?:^|[_-])(api[_-]?key|token|secret|password|credential)(?:$|[_-])',
    caseSensitive: false);

Never _invalid() => throw ArgumentError('Gateway operation is invalid');

Object? _snapshot(Object? value, List<int> budget, int depth,
    {String key = ''}) {
  if (depth > 16 || --budget[0] < 0) _invalid();
  if (value == null || value is bool || value is int) return value;
  if (value is num) return value.isFinite ? value : _invalid();
  if (value is String) {
    if (!isSafePublicText(value) && key != 'root') _invalid();
    return value;
  }
  if (value is List) {
    return List.unmodifiable(
        value.map((item) => _snapshot(item, budget, depth + 1, key: key)));
  }
  if (value is Map && value.keys.every((item) => item is String)) {
    final result = <String, Object?>{};
    for (final entry in value.entries) {
      final name = entry.key as String;
      if (_secretKey.hasMatch(name) && name != 'credential_refs') _invalid();
      result[name] = _snapshot(entry.value, budget, depth + 1, key: name);
    }
    return Map<String, Object?>.unmodifiable(result);
  }
  return _invalid();
}

Map<String, Object?> _operation(Map<String, Object?> value) =>
    _snapshot(value, [4096], 0) as Map<String, Object?>;

final class GatewayOperation {
  final String action, clientRequestId;
  final Map<String, Object?> operation;
  GatewayOperation._(
      this.action, this.clientRequestId, Map<String, Object?> operation)
      : operation = _operation(operation) {
    if (clientRequestId.trim().isEmpty || !isSafePublicText(clientRequestId)) {
      _invalid();
    }
  }

  factory GatewayOperation.pluginProbe(
          {required String name, required String clientRequestId}) =>
      GatewayOperation._('plugin.probe', clientRequestId, {'name': name});
  factory GatewayOperation.pluginCall(
          {required String name,
          required String tool,
          required Map<String, dynamic> arguments,
          required List<String> credentialRefs,
          required String clientRequestId}) =>
      GatewayOperation._('plugin.call', clientRequestId, {
        'name': name,
        'tool': tool,
        'arguments': arguments,
        'credential_refs': credentialRefs,
      });
  factory GatewayOperation.chat(String clientRequestId, String model,
          List<Map<String, dynamic>> messages) =>
      GatewayOperation._('chat.complete', clientRequestId,
          {'model': model, 'messages': messages, 'stream': true});
  factory GatewayOperation.workflow(
          String clientRequestId, Map<String, Object?> operation) =>
      GatewayOperation._('workflow.run', clientRequestId, operation);
  factory GatewayOperation.exact(
          {required String action,
          required Map<String, Object?> operation,
          required String clientRequestId}) =>
      GatewayOperation._(action, clientRequestId, operation);

  Map<String, dynamic> prepareBody(String journeyRef, String eventHead) => {
        'schema': gatewayOperationSchema,
        'journey_ref': journeyRef,
        'expected_event_head': eventHead,
        'client_request_id': clientRequestId,
        'operation': operation,
      };
  Map<String, dynamic> finalBody(
          String journeyRef, String eventHead, String grantRef) =>
      {
        'schema': gatewayOperationSchema,
        'journey_ref': journeyRef,
        'expected_event_head': eventHead,
        'client_request_id': clientRequestId,
        'grant_ref': grantRef,
        ...operation,
      };
}

final class GatewayGrantSummary extends DefensiveModel {
  final String operation, journeyRef, eventHead, tool, argumentsSha256;
  final String effect, expiresAt;
  final List<String> scopes, dataRefs, credentialRefs;
  GatewayGrantSummary._(
      this.operation,
      this.journeyRef,
      this.eventHead,
      this.tool,
      this.argumentsSha256,
      this.scopes,
      this.dataRefs,
      this.credentialRefs,
      this.effect,
      this.expiresAt,
      super.parseIssues);
  factory GatewayGrantSummary.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    _exact(
        json,
        const {
          'operation',
          'journey_ref',
          'expected_event_head',
          'tool',
          'arguments_sha256',
          'scopes',
          'data_refs',
          'credential_refs',
          'effect',
          'expires_at'
        },
        issues,
        'summary');
    return GatewayGrantSummary._(
        readText(json, 'operation', issues),
        readText(json, 'journey_ref', issues, pattern: _journeyRef),
        readText(json, 'expected_event_head', issues, pattern: sha256Pattern),
        readText(json, 'tool', issues),
        readText(json, 'arguments_sha256', issues, pattern: sha256Pattern),
        readStringList(json['scopes'], 'scopes', issues),
        readStringList(json['data_refs'], 'data_refs', issues),
        _refs(json['credential_refs'], 'credential_refs', issues),
        readText(json, 'effect', issues),
        readText(json, 'expires_at', issues),
        issues);
  }
}

final class GatewayGrantProposal extends DefensiveModel {
  final String proposalRef, plannedGrantRef, action, journeyRef, eventHead;
  final String clientRequestId,
      tool,
      operationSha256,
      argumentsSha256,
      expiresAt;
  final List<String> scopes, dataRefs, credentialRefs;
  final GatewayGrantSummary summary;
  GatewayGrantProposal._(
      this.proposalRef,
      this.plannedGrantRef,
      this.action,
      this.journeyRef,
      this.eventHead,
      this.clientRequestId,
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
    _exact(json, _proposalFields, issues, 'proposal');
    expectSchema(json, gatewayProposalSchema, issues);
    final rawSummary = json['summary'];
    final summary = rawSummary is Map<String, Object?>
        ? GatewayGrantSummary.fromJson(rawSummary)
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
    final tool = readText(json, 'tool', issues);
    final arguments =
        readText(json, 'arguments_sha256', issues, pattern: sha256Pattern);
    final scopes = readStringList(json['scopes'], 'scopes', issues);
    final data = readStringList(json['data_refs'], 'data_refs', issues);
    final credentials =
        _refs(json['credential_refs'], 'credential_refs', issues);
    final expires = readText(json, 'expires_at', issues);
    if (proposal.length == 36 &&
        grant.length == 36 &&
        proposal.substring(4) != grant.substring(4)) {
      addParseIssue(issues, 'planned_grant_ref', grant);
    }
    if (summary.operation != action ||
        summary.journeyRef != journey ||
        summary.eventHead != head ||
        summary.tool != tool ||
        summary.argumentsSha256 != arguments ||
        summary.expiresAt != expires ||
        !_same(summary.scopes, scopes) ||
        !_same(summary.dataRefs, data) ||
        !_same(summary.credentialRefs, credentials)) {
      addParseIssue(issues, 'summary', null);
    }
    return GatewayGrantProposal._(
        proposal,
        grant,
        action,
        journey,
        head,
        readText(json, 'client_request_id', issues),
        tool,
        readText(json, 'operation_sha256', issues, pattern: sha256Pattern),
        arguments,
        scopes,
        data,
        credentials,
        expires,
        summary,
        issues);
  }
}

final class GatewayGrantApproval extends DefensiveModel {
  final String grantRef, expiresAt;
  GatewayGrantApproval._(this.grantRef, this.expiresAt, super.parseIssues);
  factory GatewayGrantApproval.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    _exact(
        json, const {'schema', 'grant_ref', 'expires_at'}, issues, 'approval');
    expectSchema(json, 'flywheel.operation-grant-approval/v1', issues);
    return GatewayGrantApproval._(
        readText(json, 'grant_ref', issues, pattern: grantRefPattern),
        readText(json, 'expires_at', issues),
        issues);
  }
}

List<String> _refs(Object? raw, String field, List<ParseIssue> issues) {
  final values = readStringList(raw, field, issues);
  if (values.any((value) => !_credentialRef.hasMatch(value))) {
    addParseIssue(issues, field, raw);
    return const [];
  }
  return values;
}

void _exact(Map<String, Object?> value, Set<String> fields,
    List<ParseIssue> issues, String field) {
  if (value.keys.toSet().length != fields.length ||
      !value.keys.every(fields.contains)) {
    addParseIssue(issues, field, value.keys.toList());
  }
}

bool _same(List<String> left, List<String> right) =>
    left.length == right.length &&
    left.indexed.every((item) => item.$2 == right[item.$1]);
