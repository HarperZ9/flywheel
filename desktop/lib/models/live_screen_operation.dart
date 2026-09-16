import 'gateway_grant_models.dart';

final _id = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._:@+\-]{0,127}$');
final _model = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,159}$');

/// Capture-session authority is separate from the authority to send images to
/// a provider. This operation contains no credentials or permission to infer.
GatewayOperation openLiveScreenOperation({
  required String requestId,
  required String bodySessionRef,
  required String instrumentRef,
  required List<String> sourceIds,
  required String destination,
  required String model,
  int expiresAfterMs = 120000,
  bool startImmediately = false,
}) {
  if (!_id.hasMatch(bodySessionRef) ||
      !_id.hasMatch(instrumentRef) ||
      !_id.hasMatch(destination) ||
      !_model.hasMatch(model) ||
      sourceIds.isEmpty ||
      sourceIds.length > 16 ||
      sourceIds.toSet().length != sourceIds.length ||
      sourceIds.any((id) => !_id.hasMatch(id)) ||
      expiresAfterMs < 1000 ||
      expiresAfterMs > 120000) {
    throw ArgumentError('Invalid screen session selection');
  }
  return GatewayOperation.exact(
    action: 'live_screen.control',
    clientRequestId: requestId,
    destination: GatewayDestination('live-screen', 'open:$destination:$model'),
    credentialRefs: const [],
    dataRefs: const [],
    operation: {
      'control': 'open',
      'body_session_ref': bodySessionRef,
      'instrument_ref': instrumentRef,
      'sources': [
        for (final id in sourceIds) {'source_id': id}
      ],
      'destination': destination,
      'model': model,
      'delivery_mode': 'sampled_image',
      'expires_after_ms': expiresAfterMs,
      'start_immediately': startImmediately,
    },
  );
}

GatewayOperation controlLiveScreenOperation({
  required String requestId,
  required String sessionId,
  required String control,
}) {
  if (!_id.hasMatch(sessionId) ||
      !const {'start', 'pause', 'resume', 'stop'}.contains(control)) {
    throw ArgumentError('Invalid screen control');
  }
  return GatewayOperation.exact(
    action: 'live_screen.control',
    clientRequestId: requestId,
    destination:
        GatewayDestination('live-screen', 'session:$sessionId:$control'),
    credentialRefs: const [],
    dataRefs: const [],
    operation: {'control': control, 'session_id': sessionId},
  );
}
