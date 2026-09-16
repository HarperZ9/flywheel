import 'studio_body_protocol.dart';

class StudioBodyStatus {
  final bool backendReady;
  final String unavailableReason, bodyContractVersion, verifiedStatus;
  final List<String> availableEffectors, deliveryModes;
  final StudioBodyBuilt built;
  final StudioBodyAuthority authority;
  final StudioBodyRoutes routes;
  final StudioBodyScreenFeed screenFeed;
  const StudioBodyStatus({
    required this.backendReady,
    required this.unavailableReason,
    required this.bodyContractVersion,
    required this.verifiedStatus,
    required this.availableEffectors,
    required this.deliveryModes,
    required this.built,
    required this.authority,
    required this.routes,
    required this.screenFeed,
  });

  factory StudioBodyStatus.fromJson(Map<String, Object?> json) {
    final built = StudioBodyBuilt.fromJson(studioBodyMap(json['built']));
    final authority =
        StudioBodyAuthority.fromJson(studioBodyMap(json['authority']));
    return StudioBodyStatus(
      backendReady: json['backend_ready'] == true,
      unavailableReason: studioBodyText(json['unavailable_reason']),
      bodyContractVersion: studioBodyText(json['body_contract_version']),
      verifiedStatus: studioBodyText(studioBodyMap(json['verified'])['status']),
      availableEffectors: studioBodyStrings(json['available_effectors']),
      deliveryModes: studioBodyStrings(json['delivery_modes']),
      built: built,
      authority: authority,
      routes: StudioBodyRoutes.fromJson(studioBodyMap(json['routes'])),
      screenFeed:
          StudioBodyScreenFeed.fromJson(studioBodyMap(json['screen_feed'])),
    );
  }

  bool get canAttemptStep =>
      authority.configured &&
      built.routes &&
      (built.soundEffector || built.engineVisualEffector);
  List<String> get requiredAuthorityEnv => authority.requiredEnv;
}

class StudioBodyBuilt {
  final bool routes, snapshotContract, soundEffector, engineVisualEffector;
  final bool liveScreenPreviewGateway;
  const StudioBodyBuilt({
    required this.routes,
    required this.snapshotContract,
    required this.soundEffector,
    required this.engineVisualEffector,
    required this.liveScreenPreviewGateway,
  });
  factory StudioBodyBuilt.fromJson(Map<String, Object?> json) =>
      StudioBodyBuilt(
        routes: json['routes'] == true,
        snapshotContract: json['snapshot_contract'] == true,
        soundEffector: json['sound_effector'] == true,
        engineVisualEffector: json['engine_visual_effector'] == true,
        liveScreenPreviewGateway: json['live_screen_preview_gateway'] == true,
      );
}

class StudioBodyAuthority {
  final bool configured, available, grantRequired, grantVerified;
  final String mode;
  final List<String> requiredEnv;
  const StudioBodyAuthority({
    required this.configured,
    required this.available,
    required this.grantRequired,
    required this.grantVerified,
    required this.mode,
    required this.requiredEnv,
  });
  factory StudioBodyAuthority.fromJson(Map<String, Object?> json) =>
      StudioBodyAuthority(
        configured: json['configured'] == true,
        available: json['available'] == true,
        grantRequired: json['grant_required'] == true,
        grantVerified: json['grant_verified'] == true,
        mode: studioBodyText(json['mode']),
        requiredEnv: studioBodyStrings(json['required_env']),
      );
}

class StudioBodyRoutes {
  final String status, snapshot, step, liveScreenPreview;
  const StudioBodyRoutes({
    this.status = '',
    this.snapshot = '',
    this.step = '',
    this.liveScreenPreview = '',
  });
  factory StudioBodyRoutes.fromJson(Map<String, Object?> json) =>
      StudioBodyRoutes(
        status: studioBodyText(json['status']),
        snapshot: studioBodyText(json['snapshot']),
        step: studioBodyText(json['step']),
        liveScreenPreview: studioBodyText(json['live_screen_preview']),
      );
}

class StudioBodyScreenFeed {
  final String captureSessionRef, nativeVideo, latestFrameRef;
  final bool previewAvailable;
  final int? latestDeliveredFrameAgeMs;
  const StudioBodyScreenFeed({
    this.captureSessionRef = '',
    this.nativeVideo = '',
    this.latestFrameRef = '',
    this.previewAvailable = false,
    this.latestDeliveredFrameAgeMs,
  });
  factory StudioBodyScreenFeed.fromJson(Map<String, Object?> json) =>
      StudioBodyScreenFeed(
        captureSessionRef: studioBodyText(json['capture_session_ref']),
        nativeVideo: studioBodyText(json['native_video']),
        latestFrameRef: studioBodyText(json['latest_frame_ref']),
        previewAvailable: json['preview_available'] == true,
        latestDeliveredFrameAgeMs:
            studioBodyIntOrNull(json['latest_delivered_frame_age_ms']),
      );
}

class StudioBodySnapshotRequest {
  final String sessionRef, instrumentRef, captureSessionRef, sourceRef;
  final String latestFrameRef, frameSha256;
  final int? latestDeliveredFrameAgeMs;
  const StudioBodySnapshotRequest({
    required this.sessionRef,
    required this.instrumentRef,
    this.captureSessionRef = '',
    this.sourceRef = '',
    this.latestFrameRef = '',
    this.frameSha256 = '',
    this.latestDeliveredFrameAgeMs,
  });
  Map<String, dynamic> toJson() => {
        'session_ref': sessionRef,
        'instrument_ref': instrumentRef,
        if (captureSessionRef.isNotEmpty)
          'capture_session_ref': captureSessionRef,
        if (sourceRef.isNotEmpty) 'source_ref': sourceRef,
        if (latestFrameRef.isNotEmpty) 'latest_frame_ref': latestFrameRef,
        if (frameSha256.isNotEmpty) 'frame_sha256': frameSha256,
        if (latestDeliveredFrameAgeMs != null)
          'latest_delivered_frame_age_ms': latestDeliveredFrameAgeMs,
      };
}

class StudioBodySnapshot {
  final String snapshotId, capturedAt, sessionRef, instrumentRef, target;
  final String captureSessionRef, latestFrameRef, requestedLatestFrameRef;
  final String captureStatus, sourceRef, frameSha256;
  final int? latestDeliveredFrameAgeMs;
  final bool captureValidated;
  final List<StudioBodyObservation> observations;
  const StudioBodySnapshot({
    required this.snapshotId,
    required this.capturedAt,
    required this.sessionRef,
    required this.instrumentRef,
    required this.target,
    required this.captureSessionRef,
    required this.latestFrameRef,
    required this.requestedLatestFrameRef,
    required this.captureStatus,
    this.sourceRef = '',
    this.frameSha256 = '',
    required this.latestDeliveredFrameAgeMs,
    required this.captureValidated,
    required this.observations,
  });
  factory StudioBodySnapshot.fromJson(Map<String, Object?> json) {
    final snap = studioBodyMap(json['snapshot']);
    final capture = studioBodyMap(snap['capture']);
    final requested = studioBodyMap(snap['requested_capture']);
    return StudioBodySnapshot(
      snapshotId: studioBodyText(snap['snapshot_id']),
      capturedAt: studioBodyText(snap['captured_at']),
      sessionRef: studioBodyText(snap['session_ref']),
      instrumentRef: studioBodyText(snap['instrument_ref']),
      target: studioBodyText(snap['target']),
      captureSessionRef: studioBodyText(snap['capture_session_ref']),
      latestFrameRef: studioBodyText(snap['latest_frame_ref']),
      requestedLatestFrameRef: studioBodyText(requested['latest_frame_ref']),
      captureStatus: studioBodyText(capture['status']),
      sourceRef: studioBodyText(capture['source_ref']),
      frameSha256: studioBodyText(capture['frame_sha256']),
      latestDeliveredFrameAgeMs:
          studioBodyIntOrNull(snap['latest_delivered_frame_age_ms']),
      captureValidated:
          capture['validated'] == true && capture['available'] == true,
      observations: studioBodyRecords(
          snap['observations'], StudioBodyObservation.fromJson),
    );
  }
  StudioBodyObservation? get primaryObservation =>
      observations.isEmpty ? null : observations.first;
}

class StudioBodyObservation {
  final String observationRef,
      source,
      deliveryMode,
      stateSha256,
      latestFrameRef;
  const StudioBodyObservation({
    required this.observationRef,
    required this.source,
    required this.deliveryMode,
    required this.stateSha256,
    required this.latestFrameRef,
  });
  factory StudioBodyObservation.fromJson(Map<String, Object?> json) =>
      StudioBodyObservation(
        observationRef: studioBodyText(json['observation_ref']),
        source: studioBodyText(json['source']),
        deliveryMode: studioBodyText(json['delivery_mode']),
        stateSha256: studioBodyText(json['state_sha256']),
        latestFrameRef: studioBodyText(json['latest_frame_ref']),
      );
}
