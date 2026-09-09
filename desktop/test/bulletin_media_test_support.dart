import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/widgets.dart';
import 'package:flywheel_desktop/client/bulletin_media_api.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/models/bulletin_media_models.dart';
import 'package:flywheel_desktop/models/gateway_grant_models.dart';

const shaA = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const shaB = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const journeyRef = 'jrn_0123456789abcdef0123456789abcdef';
const eventHead =
    '1111111111111111111111111111111111111111111111111111111111111111';
const credRef = 'cred_0123456789abcdef0123456789abcdef';
const proposalRef = 'prp_0123456789abcdef0123456789abcdef';
const grantRef = 'gnt_0123456789abcdef0123456789abcdef';
const mediaId = 'AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-abcde';
const previewRef = 'data_bulletin_media_preview_0123456789abcdef';

Uint8List tinyPngBytes() => base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==');

Map<String, Object?> runJson({
  String runId = 'run_20260909T000000_abcdef123456',
  String title = 'music and art sketch',
  int artifactCount = 1,
}) =>
    {
      'run_id': runId,
      'kind': 'creative',
      'title': title,
      'status': 'created',
      'created_utc': '2026-09-09T12:00:00Z',
      'updated_utc': '2026-09-09T12:00:00Z',
      'artifact_count': artifactCount,
    };

Map<String, Object?> runsResponseJson({
  String runId = 'run_20260909T000000_abcdef123456',
  String title = 'music and art sketch',
}) =>
    {
      'schema': 'flywheel.bulletin-media-runs-response/v1',
      'runs': [runJson(runId: runId, title: title)],
      'next_cursor': null,
    };

Map<String, Object?> artifactJson({String? label, String? kind}) => {
      'artifact_id': 'artifact_meme_png',
      'label': label ?? 'Meme preview PNG',
      'kind': kind ?? 'image',
      'media_type': 'image/png',
      'bytes': tinyPngBytes().length,
      'sha256': shaA,
      'expected_media_id': mediaId,
      'created_utc': '2026-09-09T12:00:00Z',
    };

Map<String, Object?> artifactsResponseJson({
  String runId = 'run_20260909T000000_abcdef123456',
}) =>
    {
      'schema': 'flywheel.bulletin-media-artifacts-response/v1',
      'run_id': runId,
      'artifacts': [artifactJson()],
    };

Map<String, Object?> reviewJson({
  String kind = 'image',
  String mediaType = 'image/png',
  String attachmentSha = shaA,
  String ref = previewRef,
  Map<String, Object?> extra = const {},
}) =>
    {
      'schema': 'flywheel.bulletin-media-review/v1',
      'mode': 'artifact_share',
      'destination': {'base_url': 'https://bulletin.example.test'},
      'effect': 'upload these public bytes, then publish this post once',
      'post': {
        'room': 'outcome-bulletin',
        'body': 'The final public post body.'
      },
      'body_sha256': shaA,
      'post_payload_sha256': shaB,
      'media_list_sha256': shaA,
      'packet_sha256': shaB,
      'preview_sha256': shaA,
      'attachments': [
        {
          'artifact_id': 'artifact_meme_png',
          'media_id': mediaId,
          'expected_media_id': mediaId,
          'preview_ref': ref,
          'label': 'Meme preview PNG',
          'kind': kind,
          'media_type': mediaType,
          'bytes': tinyPngBytes().length,
          'sha256': attachmentSha,
          'alt': 'One pixel meme preview.',
        }
      ],
      'preview_media': [
        {
          'media_id': mediaId,
          'preview_ref': ref,
          'kind': kind,
          'media_type': mediaType,
          'bytes': tinyPngBytes().length,
        }
      ],
      'does_not_prove': [
        'semantic truth of the post body',
        'license, authorship, malware safety, or hidden-data absence',
      ],
      ...extra,
    };

Map<String, Object?> proposalJson({Map<String, Object?>? review}) => {
      'schema': gatewayProposalSchema,
      'proposal_ref': proposalRef,
      'planned_grant_ref': grantRef,
      'action': 'lane.call',
      'journey_ref': journeyRef,
      'expected_event_head': eventHead,
      'client_request_id': 'bulletin_media_request_001',
      'destination': {'kind': 'lane', 'ref': 'bulletin'},
      'tool': 'board_publish_media_post',
      'operation_sha256': shaA,
      'arguments_sha256': shaB,
      'scopes': ['exec', 'network', 'plugin', 'secrets'],
      'data_refs': [previewRef],
      'credential_refs': [credRef],
      'expires_at': '2026-09-09T12:02:00Z',
      'summary': {
        'schema': gatewayGrantSummarySchema,
        'action': 'lane.call',
        'journey_ref': journeyRef,
        'expected_event_head': eventHead,
        'destination': {'kind': 'lane', 'ref': 'bulletin'},
        'tool': 'board_publish_media_post',
        'operation_sha256': shaA,
        'arguments_sha256': shaB,
        'scopes': ['exec', 'network', 'plugin', 'secrets'],
        'data_refs': [previewRef],
        'credential_refs': [credRef],
        'effect': 'one dispatch after approval',
        'expires_at': '2026-09-09T12:02:00Z',
        'bulletin_media_review': review ?? reviewJson(),
      },
    };

Map<String, Object?> operationJson({
  Map<String, Object?>? review,
  String clientRequestId = 'bulletin_media_request_001',
}) =>
    {
      'schema': gatewayOperationSchema,
      'action': 'lane.call',
      'journey_ref': journeyRef,
      'expected_event_head': eventHead,
      'client_request_id': clientRequestId,
      'operation': {
        'name': 'bulletin',
        'tool': 'board_publish_media_post',
        'args': {
          'schema': 'flywheel.outcome-bulletin-media-preview/v1',
          'preview_sha256': shaA,
          'destination': {'base_url': 'https://bulletin.example.test'},
          'post': {
            'room': 'outcome-bulletin',
            'body': 'The final public post body.',
            'attachments': [
              {'media_id': mediaId, 'alt': 'One pixel meme preview.'}
            ],
          },
          'media': [
            {
              'expected_media_id': mediaId,
              'sha256': shaA,
              'bytes': tinyPngBytes().length,
              'media_type': 'image/png',
              'kind': 'image'
            }
          ],
          'review': review ?? reviewJson(),
          'preview_media': [
            {
              'media_id': mediaId,
              'preview_ref': previewRef,
              'kind': 'image',
              'media_type': 'image/png',
              'bytes': tinyPngBytes().length,
            }
          ],
          'data_refs': [previewRef],
        },
        'governance_tier': 'T2',
        'timeout': 20,
        'data_refs': [previewRef],
        'credential_refs': [credRef],
      },
    };

Map<String, Object?> previewResponseJson({
  Map<String, Object?>? review,
  String clientRequestId = 'bulletin_media_request_001',
}) =>
    {
      'schema': 'flywheel.outcome-bulletin-media-preview-response/v1',
      'proposal': proposalJson(review: review),
      'operation':
          operationJson(review: review, clientRequestId: clientRequestId),
    };

Map<String, Object?> publishResultJson(String state) => {
      'schema': 'flywheel.outcome-bulletin-media-result/v1',
      'state': state,
      if (state == 'posted_readback_match') 'post_id': 'post_abc123',
      'media_ids': [mediaId],
      'message': 'Synthetic result for tests.',
    };

final class FakeBulletinMediaApi implements BulletinMediaApi {
  List<BulletinMediaRun> runs;
  List<BulletinMediaArtifact> artifacts;
  BulletinMediaPreviewResponse preview;
  BulletinMediaPublishResult result;
  List<BulletinMediaCredentialHandle> credentialRows;
  BulletinMediaDraft? lastDraft;
  Map<String, dynamic>? lastFinalBody;
  Object? credentialError;
  int previewCalls = 0;

  FakeBulletinMediaApi({
    List<BulletinMediaRun>? runs,
    List<BulletinMediaArtifact>? artifacts,
    List<BulletinMediaCredentialHandle>? credentialRows,
    this.credentialError,
    BulletinMediaPreviewResponse? preview,
    BulletinMediaPublishResult? result,
  })  : runs = runs ?? [BulletinMediaRun.fromJson(runJson(), 'runs[0]')],
        artifacts = artifacts ?? [BulletinMediaArtifact.fromJson(artifactJson(), 'artifact')],
        credentialRows = credentialRows ?? const [
          BulletinMediaCredentialHandle(
              credentialRef: credRef, credentialName: bulletinAgentJwkCredentialName)
        ],
        preview = preview ??
            BulletinMediaPreviewResponse.fromJson(previewResponseJson()),
        result = result ?? BulletinMediaPublishResult.fromJson(
            publishResultJson('posted_readback_match'));

  @override
  Future<List<BulletinMediaCredentialHandle>> credentialHandles() async =>
      credentialError == null ? credentialRows : throw credentialError!;

  @override
  Future<List<BulletinMediaRun>> listRuns(
          {int limit = 50, String? cursor}) async =>
      runs;

  @override
  Future<List<BulletinMediaArtifact>> listArtifacts(String runId) async => artifacts;

  @override
  Future<BulletinMediaPreviewResponse> previewDraft(
      BulletinMediaDraft draft) async {
    previewCalls++;
    lastDraft = draft;
    return preview;
  }

  @override
  Future<BulletinMediaPublishResult> publish(
      Map<String, dynamic> finalBody) async {
    lastFinalBody = finalBody;
    return result;
  }
}

Future<GatewayAuthorizationOutcome<BulletinMediaPublishResult>>
    approvingBulletinAuthorizer(
  BuildContext context,
  BulletinMediaPreviewResponse preview,
  GatewayOperationSupplier currentOperation,
  Future<BulletinMediaPublishResult> Function(Map<String, dynamic>) dispatch,
) async {
  final operation = preview.operation!;
  if (currentOperation() != operation) {
    return const GatewayAuthorizationOutcome.failure(GatewayOperationFailure(
        'OPERATION_CHANGED', 'Operation changed; approval was not used'));
  }
  final body = operation.finalBody(
    const GatewayJourneyBinding(journeyRef, eventHead),
    grantRef,
  );
  return GatewayAuthorizationOutcome.value(await dispatch(body));
}
