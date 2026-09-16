import 'studio_body_protocol.dart';

class StudioBodyStepDraft {
  final String clientActionId, idempotencyKey, modelRouteRef, observationRef;
  final String actionKind, target, captureSessionRef, latestFrameRef;
  final int? latestDeliveredFrameAgeMs;
  final Map<String, dynamic> actionArgs;
  final Map<String, dynamic>? modelDelivery;
  const StudioBodyStepDraft._({
    required this.clientActionId,
    required this.idempotencyKey,
    required this.modelRouteRef,
    required this.observationRef,
    required this.actionKind,
    required this.target,
    required this.actionArgs,
    this.captureSessionRef = '',
    this.latestFrameRef = '',
    this.latestDeliveredFrameAgeMs,
    this.modelDelivery,
  });
  factory StudioBodyStepDraft.sound({
    required String clientActionId,
    required String idempotencyKey,
    required String modelRouteRef,
    required String observationRef,
    required String sessionRef,
    required String instrumentRef,
    required int seed,
    required double durationSeconds,
    required double rootHz,
    String captureSessionRef = '',
    String latestFrameRef = '',
    int? latestDeliveredFrameAgeMs,
    Map<String, dynamic>? modelDelivery,
  }) =>
      StudioBodyStepDraft._(
        clientActionId: clientActionId,
        idempotencyKey: idempotencyKey,
        modelRouteRef: modelRouteRef,
        observationRef: observationRef,
        actionKind: studioBodySoundActionKind,
        target: '$studioBodySoundTargetPrefix$sessionRef/$instrumentRef',
        actionArgs: {
          'seed': seed,
          'duration_s': durationSeconds,
          'root_hz': rootHz
        },
        captureSessionRef: captureSessionRef,
        latestFrameRef: latestFrameRef,
        latestDeliveredFrameAgeMs: latestDeliveredFrameAgeMs,
        modelDelivery: modelDelivery,
      );
  factory StudioBodyStepDraft.engine({
    required String clientActionId,
    required String idempotencyKey,
    required String modelRouteRef,
    required String observationRef,
    required String sessionRef,
    required String instrumentRef,
    required int seed,
    String generator = 'gyroid',
    String scheme = 'analogous',
    int maxSteps = 4,
    double targetScore = 0.9,
    double floor = 0.6,
    String captureSessionRef = '',
    String latestFrameRef = '',
    int? latestDeliveredFrameAgeMs,
    Map<String, dynamic>? modelDelivery,
  }) =>
      StudioBodyStepDraft._(
        clientActionId: clientActionId,
        idempotencyKey: idempotencyKey,
        modelRouteRef: modelRouteRef,
        observationRef: observationRef,
        actionKind: studioBodyEngineActionKind,
        target: '$studioBodyEngineTargetPrefix$sessionRef/$instrumentRef',
        actionArgs: {
          'seed': seed,
          'generator': generator,
          'scheme': scheme,
          'max_steps': maxSteps,
          'target': targetScore,
          'floor': floor,
          'render_frames': true
        },
        captureSessionRef: captureSessionRef,
        latestFrameRef: latestFrameRef,
        latestDeliveredFrameAgeMs: latestDeliveredFrameAgeMs,
        modelDelivery: modelDelivery,
      );
  Map<String, dynamic> toJson() => {
        'schema': studioBodyContractVersion,
        'client_action_id': clientActionId,
        'idempotency_key': idempotencyKey,
        'model_route_ref': modelRouteRef,
        'observation_ref': observationRef,
        if (captureSessionRef.isNotEmpty)
          'capture_session_ref': captureSessionRef,
        if (latestFrameRef.isNotEmpty) 'latest_frame_ref': latestFrameRef,
        if (latestDeliveredFrameAgeMs != null)
          'latest_delivered_frame_age_ms': latestDeliveredFrameAgeMs,
        if (modelDelivery != null) 'model_delivery': modelDelivery,
        'action': {'kind': actionKind, 'target': target, 'args': actionArgs},
      };
}

class StudioBodyStepResult {
  final bool accepted;
  final String status, actionKind, target;
  final Map<String, dynamic> receipt, authorityReceipt;
  final List<String> errors;
  const StudioBodyStepResult({
    required this.accepted,
    required this.status,
    required this.actionKind,
    required this.target,
    required this.receipt,
    required this.authorityReceipt,
    required this.errors,
  });
  factory StudioBodyStepResult.fromJson(Map<String, Object?> json) =>
      StudioBodyStepResult(
        accepted: json['accepted'] == true,
        status: studioBodyText(json['status']),
        actionKind: studioBodyText(json['action_kind']),
        target: studioBodyText(json['target']),
        receipt:
            Map<String, dynamic>.unmodifiable(studioBodyMap(json['receipt'])),
        authorityReceipt: Map<String, dynamic>.unmodifiable(
            studioBodyMap(json['authority_receipt'])),
        errors: studioBodyStrings(json['errors']),
      );
  bool get verifiedDelivery =>
      accepted &&
      authorityReceipt['decision'] == 'allow' &&
      authorityReceipt['acted'] == true &&
      authorityReceipt['verified'] == true;
  String get authorityDecision => studioBodyText(authorityReceipt['decision']);
  String receiptText(String key) => studioBodyText(receipt[key]);
}
