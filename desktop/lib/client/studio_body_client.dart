import '../models/studio_body_models.dart';
import 'gateway_client.dart';

abstract interface class StudioBodyApi {
  Future<StudioBodyStatus> status();
  Future<StudioBodySnapshot> snapshot(StudioBodySnapshotRequest request);
  Future<StudioBodyStepResult> submitStep(StudioBodyStepDraft draft);
}

final class GatewayStudioBodyClient implements StudioBodyApi {
  final GatewayClient _client;
  const GatewayStudioBodyClient(this._client);

  @override
  Future<StudioBodyStatus> status() async =>
      StudioBodyStatus.fromJson(Map<String, Object?>.from(
          await _client.getJson('/api/studio/body/status')));

  @override
  Future<StudioBodySnapshot> snapshot(
          StudioBodySnapshotRequest request) async =>
      StudioBodySnapshot.fromJson(Map<String, Object?>.from(
        await _client.postJsonNoRedirect(
          '/api/studio/body/snapshot',
          request.toJson(),
          timeout: const Duration(seconds: 20),
        ),
      ));

  @override
  Future<StudioBodyStepResult> submitStep(StudioBodyStepDraft draft) async =>
      StudioBodyStepResult.fromJson(Map<String, Object?>.from(
        await _client.postJsonNoRedirect(
          '/api/studio/body/step',
          draft.toJson(),
          timeout: const Duration(seconds: 60),
          acceptedStatuses: const {200, 400, 403, 503},
        ),
      ));
}
