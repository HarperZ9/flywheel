import 'evidence_state.dart';
import 'gateway_grant_models.dart';
import 'bulletin_media_review.dart';

const bulletinArtifactsRequestSchema =
    'flywheel.bulletin-media-artifacts-request/v1';
const bulletinArtifactsResponseSchema =
    'flywheel.bulletin-media-artifacts-response/v1';
const bulletinArtifactSchema = 'flywheel.outcome-bulletin-media-artifact/v1';
const bulletinArtifactListSchema =
    'flywheel.outcome-bulletin-media-artifact-list/v1';
const bulletinSelectionSchema = 'flywheel.outcome-bulletin-media-selection/v1';
const bulletinPreparedPreviewSchema =
    'flywheel.outcome-bulletin-media-preview-response/v1';

final _artifactId = RegExp(r'^artifact_[A-Za-z0-9._:-]{1,96}$');
final _runId = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$');
final _requestId = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$');
final _credentialRef = RegExp(r'^cred_[0-9a-f]{32}$');
final _backendMediaId = RegExp(r'^[A-Za-z0-9_-]{16,128}$');

final class BulletinMediaArtifact extends DefensiveModel {
  final String artifactId,
      label,
      mediaType,
      sha256,
      expectedMediaId,
      createdUtc;
  final BulletinMediaKind kind;
  final int bytes;
  BulletinMediaArtifact._(
      this.artifactId,
      this.label,
      this.kind,
      this.mediaType,
      this.bytes,
      this.sha256,
      this.expectedMediaId,
      this.createdUtc,
      super.parseIssues);

  factory BulletinMediaArtifact.fromJson(Map<String, Object?> json, String f) {
    final issues = <ParseIssue>[];
    final fields = {
      if (json.containsKey('schema')) 'schema',
      'artifact_id',
      'label',
      'kind',
      'media_type',
      'bytes',
      'sha256',
      if (json.containsKey('expected_media_id')) 'expected_media_id',
      if (json.containsKey('created_utc')) 'created_utc'
    };
    bulletinExact(json, fields, issues, f);
    if (json.containsKey('schema')) {
      expectSchema(json, bulletinArtifactSchema, issues);
    }
    return BulletinMediaArtifact._(
      readText(json, 'artifact_id', issues, pattern: _artifactId),
      readText(json, 'label', issues),
      bulletinMediaKind(json['kind'], '$f.kind', issues),
      readText(json, 'media_type', issues, pattern: bulletinMediaTypePattern),
      bulletinReadNonNegativeInt(json, 'bytes', issues),
      readText(json, 'sha256', issues, pattern: sha256Pattern),
      readText(json, 'expected_media_id', issues,
          optional: true, pattern: _backendMediaId),
      readText(json, 'created_utc', issues, optional: true),
      issues,
    );
  }
}

final class BulletinMediaArtifactsResponse extends DefensiveModel {
  final String runId;
  final List<BulletinMediaArtifact> artifacts;
  BulletinMediaArtifactsResponse._(
      this.runId, this.artifacts, super.parseIssues);

  factory BulletinMediaArtifactsResponse.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    bulletinExact(
        json, const {'schema', 'run_id', 'artifacts'}, issues, 'artifacts');
    expectSchema(json, bulletinArtifactsResponseSchema, issues);
    final runId = readText(json, 'run_id', issues, pattern: _runId);
    final rows = json['artifacts'];
    final artifacts = <BulletinMediaArtifact>[];
    if (rows is List) {
      for (var i = 0; i < rows.length; i++) {
        final row = rows[i];
        if (row is Map<String, Object?>) {
          final parsed = BulletinMediaArtifact.fromJson(row, 'artifacts[$i]');
          issues.addAll(parsed.parseIssues);
          artifacts.add(parsed);
        } else {
          addParseIssue(issues, 'artifacts[$i]', row);
        }
      }
    } else {
      addParseIssue(issues, 'artifacts', rows);
    }
    return BulletinMediaArtifactsResponse._(
        runId, List.unmodifiable(artifacts), issues);
  }
}

final class BulletinSelectedMedia {
  final BulletinMediaArtifact artifact;
  final String alt;
  const BulletinSelectedMedia(this.artifact, this.alt);

  Map<String, Object?> toJson() => {
        'artifact_id': artifact.artifactId,
        'alt': alt,
      };
}

final class BulletinMediaDraft {
  final String runId, journeyRef, eventHead, clientRequestId, credentialRef;
  final Uri destination;
  final String room, title, description, sourceAttribution;
  final List<String> limits;
  final List<BulletinSelectedMedia> media;
  const BulletinMediaDraft({
    required this.runId,
    required this.journeyRef,
    required this.eventHead,
    required this.clientRequestId,
    required this.credentialRef,
    required this.destination,
    required this.room,
    required this.title,
    required this.description,
    required this.sourceAttribution,
    required this.limits,
    required this.media,
  });

  bool get valid =>
      _runId.hasMatch(runId) &&
      _requestId.hasMatch(clientRequestId) &&
      _credentialRef.hasMatch(credentialRef) &&
      journeyRef.isNotEmpty &&
      eventHead.isNotEmpty &&
      destination.hasAuthority &&
      media.isNotEmpty &&
      [room, title, description, sourceAttribution]
          .every((v) => v.isNotEmpty && isSafePublicText(v)) &&
      media.every((row) => row.alt.isNotEmpty && isSafePublicText(row.alt));

  Map<String, Object?> toJson() => {
        'schema': bulletinSelectionSchema,
        'journey_ref': journeyRef,
        'expected_event_head': eventHead,
        'client_request_id': clientRequestId,
        'credential_ref': credentialRef,
        'run_id': runId,
        'destination': {'base_url': destination.toString()},
        'post': {
          'room': room,
          'title': title,
          'description': description,
          'source_attribution': sourceAttribution,
          'limits': limits,
          'links': const <Object>[],
        },
        'media': media.map((row) => row.toJson()).toList(),
      };
}

final class BulletinMediaPreviewResponse extends DefensiveModel {
  final GatewayGrantProposal proposal;
  final BulletinMediaReview review;
  final GatewayOperation? operation;
  BulletinMediaPreviewResponse._(
      this.proposal, this.review, this.operation, super.parseIssues);

  bool get canDispatch => operation != null && !invalidResponse;

  factory BulletinMediaPreviewResponse.fromJson(Map<String, Object?> json) {
    if (json['schema'] == gatewayProposalSchema) {
      return _fromProposal(json, null);
    }
    final issues = <ParseIssue>[];
    bulletinExact(
        json, const {'schema', 'proposal', 'operation'}, issues, 'preview');
    expectSchema(json, bulletinPreparedPreviewSchema, issues);
    final proposalRaw = json['proposal'];
    final proposalMap = proposalRaw is Map<String, Object?>
        ? proposalRaw
        : const <String, Object?>{};
    final proposal = GatewayGrantProposal.fromJson(proposalMap);
    issues.addAll(proposal.parseIssues);
    return _fromProposal(proposalMap, json['operation'], parentIssues: issues);
  }

  static BulletinMediaPreviewResponse _fromProposal(
      Map<String, Object?> proposalJson, Object? operationRaw,
      {List<ParseIssue>? parentIssues}) {
    final issues = parentIssues ?? <ParseIssue>[];
    final proposal = GatewayGrantProposal.fromJson(proposalJson);
    if (parentIssues == null) issues.addAll(proposal.parseIssues);
    final review = proposal.summary.bulletinMediaReview ??
        BulletinMediaReview.fromJson(const {});
    issues.addAll(review.parseIssues);
    final operation = _readOperation(operationRaw, issues);
    if (operation != null &&
        !_operationMatchesProposal(proposal, operationRaw, operation)) {
      addParseIssue(issues, 'operation', null);
    }
    if (operation == null) addParseIssue(issues, 'operation', null);
    return BulletinMediaPreviewResponse._(proposal, review, operation, issues);
  }

  static GatewayOperation? _readOperation(
      Object? raw, List<ParseIssue> issues) {
    if (raw is! Map<String, Object?>) return null;
    try {
      bulletinExact(
          raw,
          const {
            'schema',
            'action',
            'journey_ref',
            'expected_event_head',
            'client_request_id',
            'operation'
          },
          issues,
          'operation');
      expectSchema(raw, gatewayOperationSchema, issues);
      final body = raw['operation'];
      if (body is! Map<String, Object?>) return null;
      final data = _strings(body['data_refs']);
      final credentials = _strings(body['credential_refs']);
      return GatewayOperation.exact(
        action: readText(raw, 'action', issues),
        clientRequestId: readText(raw, 'client_request_id', issues),
        operation: body,
        dataRefs: data,
        credentialRefs: credentials,
      );
    } on Object {
      addParseIssue(issues, 'operation', null);
      return null;
    }
  }
}

bool _operationMatchesProposal(
    GatewayGrantProposal proposal, Object? raw, GatewayOperation operation) {
  if (raw is! Map<String, Object?>) return false;
  return raw['action'] == proposal.action &&
      raw['journey_ref'] == proposal.journeyRef &&
      raw['expected_event_head'] == proposal.eventHead &&
      raw['client_request_id'] == proposal.clientRequestId &&
      operation.destination == proposal.destination &&
      operation.tool == proposal.tool &&
      sameGatewayStringList(operation.scopes, proposal.scopes) &&
      sameGatewayStringList(operation.dataRefs, proposal.dataRefs) &&
      sameGatewayStringList(operation.credentialRefs, proposal.credentialRefs);
}

List<String>? _strings(Object? raw) =>
    raw is List && raw.every((v) => v is String)
        ? List<String>.from(raw)
        : null;
