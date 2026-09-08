import '../models/index_workspace_map.dart';
import 'gateway_client.dart';

abstract interface class IndexWorkspaceMapApi {
  Future<Map<String, dynamic>> summary(String root);
  Future<IndexWorkspaceMapJob> start(
    String root, {
    int maxDocs = 500,
    bool noCache = false,
  });
  Future<IndexWorkspaceMapJob> status(String root, {String? jobId});
  Future<IndexWorkspaceMapJob> result(String root, {String? jobId});
  Future<IndexWorkspaceMapJob> cancel(String root, {String? jobId});
  Future<IndexWorkspaceMapJob> resume(String root, {String? jobId});
}

final class GatewayIndexWorkspaceMapApi implements IndexWorkspaceMapApi {
  final GatewayClient _client;
  const GatewayIndexWorkspaceMapApi(this._client);

  @override
  Future<Map<String, dynamic>> summary(String root) =>
      _client.postJson('/api/index/summary', {'root': root});

  @override
  Future<IndexWorkspaceMapJob> start(
    String root, {
    int maxDocs = 500,
    bool noCache = false,
  }) async {
    final json = await _client.postJson('/api/index/workspace-map/start', {
      'root': root,
      'max_docs': maxDocs,
      'no_cache': noCache,
    });
    return IndexWorkspaceMapJob.fromJson(json);
  }

  @override
  Future<IndexWorkspaceMapJob> status(String root, {String? jobId}) =>
      _job('/api/index/workspace-map/status', root, jobId);

  @override
  Future<IndexWorkspaceMapJob> result(String root, {String? jobId}) =>
      _job('/api/index/workspace-map/result', root, jobId);

  @override
  Future<IndexWorkspaceMapJob> cancel(String root, {String? jobId}) =>
      _job('/api/index/workspace-map/cancel', root, jobId);

  @override
  Future<IndexWorkspaceMapJob> resume(String root, {String? jobId}) =>
      _job('/api/index/workspace-map/resume', root, jobId);

  Future<IndexWorkspaceMapJob> _job(
    String path,
    String root,
    String? jobId,
  ) async {
    final body = <String, dynamic>{'root': root};
    if (jobId != null && jobId.isNotEmpty) body['job_id'] = jobId;
    return IndexWorkspaceMapJob.fromJson(await _client.postJson(path, body));
  }
}
