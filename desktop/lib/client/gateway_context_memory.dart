part of 'gateway_client.dart';

const contextMemoryCaptureRequestSchema =
    'flywheel.context-memory-capture-request/v1';
const contextMemoryPreflightRequestSchema =
    'flywheel.context-memory-preflight-request/v1';

extension GatewayContextMemory on GatewayClient {
  /// POST /api/context-memory/status — configured Canon context bridge status.
  Future<Map<String, dynamic>> contextMemoryStatus() =>
      postJson('/api/context-memory/status', const {});

  /// POST /api/context-memory/capture — capture owner-bound context.
  Future<Map<String, dynamic>> contextMemoryCapture({
    required String projectRef,
    required Map<String, Object?> event,
    String? configGeneration,
    String? canonStoreId,
  }) =>
      postJson('/api/context-memory/capture', {
        'schema': contextMemoryCaptureRequestSchema,
        'project_ref': projectRef,
        if (configGeneration != null) 'config_generation': configGeneration,
        if (canonStoreId != null) 'canon_store_id': canonStoreId,
        'event': event,
      });

  /// POST /api/context-memory/preflight — search before assuming context is new.
  Future<Map<String, dynamic>> contextMemoryPreflight({
    required String projectRef,
    required String query,
    String? configGeneration,
    String? canonStoreId,
    int topK = 10,
    bool includePendingExtraction = true,
  }) =>
      postJson('/api/context-memory/preflight', {
        'schema': contextMemoryPreflightRequestSchema,
        'project_ref': projectRef,
        if (configGeneration != null) 'config_generation': configGeneration,
        if (canonStoreId != null) 'canon_store_id': canonStoreId,
        'query': query,
        'top_k': topK,
        'include_pending_extraction': includePendingExtraction,
      });
}
