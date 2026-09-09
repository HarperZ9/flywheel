import 'dart:convert';

import '../models/bulletin_media_models.dart';
import 'gateway_client.dart';
import 'gateway_registry.dart';

const bulletinAgentJwkCredentialName = 'BULLETIN_AGENT_JWK';
const bulletinCredentialHandleListSchema = 'flywheel.credential-handle-list/v1';
final _bulletinCredentialRef = RegExp(r'^cred_[0-9a-f]{32}$');

abstract interface class BulletinMediaApi {
  Future<List<BulletinMediaCredentialHandle>> credentialHandles();
  Future<List<BulletinMediaRun>> listRuns({int limit = 50, String? cursor});
  Future<List<BulletinMediaArtifact>> listArtifacts(String runId);
  Future<BulletinMediaPreviewResponse> previewDraft(BulletinMediaDraft draft);
  Future<BulletinMediaPublishResult> publish(Map<String, dynamic> finalBody);
}

final class BulletinMediaCredentialHandle {
  final String credentialRef, credentialName;
  const BulletinMediaCredentialHandle({
    required this.credentialRef,
    required this.credentialName,
  });

  bool get isBulletinAgentJwk =>
      credentialName == bulletinAgentJwkCredentialName;

  static BulletinMediaCredentialHandle? fromJson(Object? raw) {
    if (raw is! Map ||
        raw.length != 2 ||
        !raw.containsKey('credential_ref') ||
        !raw.containsKey('credential_name')) {
      return null;
    }
    final ref = raw['credential_ref'];
    final name = raw['credential_name'];
    if (ref is! String ||
        name is! String ||
        !_bulletinCredentialRef.hasMatch(ref) ||
        name.isEmpty) {
      return null;
    }
    return BulletinMediaCredentialHandle(
        credentialRef: ref, credentialName: name);
  }
}

final class BulletinMediaCredentialHandlesResponse {
  final List<BulletinMediaCredentialHandle> handles;
  final bool invalidResponse;
  const BulletinMediaCredentialHandlesResponse._(
      this.handles, this.invalidResponse);

  factory BulletinMediaCredentialHandlesResponse.fromJson(
      Map<String, Object?> json) {
    var invalid = json.length != 2 ||
        json['schema'] != bulletinCredentialHandleListSchema;
    final raw = json['handles'];
    final rows = <BulletinMediaCredentialHandle>[];
    final seen = <String>{};
    if (raw is List) {
      for (final item in raw) {
        final handle = BulletinMediaCredentialHandle.fromJson(item);
        if (handle == null || !seen.add(handle.credentialRef)) {
          invalid = true;
        } else if (handle.isBulletinAgentJwk) {
          rows.add(handle);
        }
      }
    } else {
      invalid = true;
    }
    return BulletinMediaCredentialHandlesResponse._(
        List.unmodifiable(rows), invalid);
  }
}

final class GatewayByteResponse {
  final int statusCode;
  final Map<String, String> headers;
  final List<int> bodyBytes;
  const GatewayByteResponse(this.statusCode, this.headers, this.bodyBytes);
}

final class GatewayBulletinMediaApi implements BulletinMediaApi {
  final GatewayClient _client;
  const GatewayBulletinMediaApi(this._client);

  @override
  Future<List<BulletinMediaCredentialHandle>> credentialHandles() async {
    final response = BulletinMediaCredentialHandlesResponse.fromJson(
        Map<String, Object?>.from(await _client.credentialHandles()));
    if (response.invalidResponse) {
      throw const FormatException('Credential handle response is invalid');
    }
    return response.handles;
  }

  @override
  Future<List<BulletinMediaRun>> listRuns(
      {int limit = 50, String? cursor}) async {
    final response = BulletinMediaRunsResponse.fromJson(
        Map<String, Object?>.from(
            await _client.postJson('/api/gateway-grants/bulletin-media-runs', {
      'schema': bulletinRunsRequestSchema,
      if (limit != 50) 'limit': limit.clamp(1, 100),
      if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
    })));
    return List.unmodifiable(
        response.runs.where((row) => !row.invalidResponse));
  }

  @override
  Future<List<BulletinMediaArtifact>> listArtifacts(String runId) async {
    final response = BulletinMediaArtifactsResponse.fromJson(
        Map<String, Object?>.from(await _client.postJson(
      '/api/gateway-grants/bulletin-media-artifacts',
      {'schema': bulletinArtifactsRequestSchema, 'run_id': runId},
    )));
    if (response.runId != runId) return const [];
    return List.unmodifiable(
        response.artifacts.where((row) => !row.invalidResponse));
  }

  @override
  Future<BulletinMediaPreviewResponse> previewDraft(
          BulletinMediaDraft draft) async =>
      BulletinMediaPreviewResponse.fromJson(Map<String, Object?>.from(
          await _client.postJson('/api/gateway-grants/bulletin-media-preview',
              Map<String, dynamic>.from(draft.toJson()))));

  Future<GatewayByteResponse> previewBytes(
      String proposalRef, String previewRef, String previewSha256) async {
    final body = await _client.postJsonNoRedirect(
      '/api/gateway-grants/bulletin-media-preview-bytes',
      {
        'schema': 'flywheel.bulletin-media-preview-bytes-request/v1',
        'proposal_ref': proposalRef,
        'preview_ref': previewRef,
        'preview_sha256': previewSha256,
      },
      timeout: const Duration(seconds: 30),
    );
    final raw = body['body_b64'];
    final bytes = raw is String ? base64Decode(raw) : const <int>[];
    return GatewayByteResponse(
        200,
        {
          'content-type': body['content_type']?.toString() ?? '',
          'content-length': body['bytes']?.toString() ?? '',
          'x-flywheel-sha256': body['sha256']?.toString() ?? '',
        },
        bytes);
  }

  @override
  Future<BulletinMediaPublishResult> publish(
      Map<String, dynamic> finalBody) async {
    final lane = finalBody['name'];
    final tool = finalBody['tool'];
    if (lane is! String || tool is! String) {
      return BulletinMediaPublishResult.fromJson(const {});
    }
    return BulletinMediaPublishResult.fromJson(Map<String, Object?>.from(
        await _client.postJsonLenient('/api/lane/$lane/$tool', finalBody,
            timeout: const Duration(seconds: 120))));
  }
}
