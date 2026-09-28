import 'package:flutter/foundation.dart' show visibleForTesting;
import '../controllers/live_screen_sharing.dart';
import '../controllers/rowan_walkthrough_operation_host.dart';
import 'live_screen_models.dart';
import 'studio_body_protocol.dart';
/// Matches the live-screen delivery operation schema upper bound for max_age_ms.
/// The backend stale receipt remains authoritative when the approved operation
/// used a stricter limit; this client cutoff expires replayed UI state that is
/// too old for a Studio action even when the event does not expose max_age_ms.
const studioBodyActionDeliveryFreshnessLimit = Duration(minutes: 2);
class StudioBodyBinding {
  final String sessionRef, instrumentRef, captureSessionRef, sourceRef;
  final String latestFrameRef, frameSha256, modelRouteRef, model;
  final String deliveryRef, deliveryReceiptSha256;
  final int? latestDeliveredFrameAgeMs;
  final int aggregateSequence;
  final List<String> gaps;
  final bool _currentDeliveredFrame, _routeMatches, _modelMatches;
  final bool _selectedModelMatches, _nonstaleDelivery;
  const StudioBodyBinding._({
    required this.sessionRef,
    required this.instrumentRef,
    required this.captureSessionRef,
    required this.sourceRef,
    required this.latestFrameRef,
    required this.frameSha256,
    required this.modelRouteRef,
    required this.model,
    required this.deliveryRef,
    required this.deliveryReceiptSha256,
    required this.latestDeliveredFrameAgeMs,
    required this.aggregateSequence,
    required this.gaps,
    required bool currentDeliveredFrame,
    required bool routeMatches,
    required bool modelMatches,
    required bool selectedModelMatches,
    required bool nonstaleDelivery,
  })  : _currentDeliveredFrame = currentDeliveredFrame,
        _routeMatches = routeMatches,
        _modelMatches = modelMatches,
        _selectedModelMatches = selectedModelMatches,
        _nonstaleDelivery = nonstaleDelivery;
  factory StudioBodyBinding.none(
          [String reason = 'No current Live Screen session']) =>
      StudioBodyBinding._(
        sessionRef: '',
        instrumentRef: '',
        captureSessionRef: '',
        sourceRef: '',
        latestFrameRef: '',
        frameSha256: '',
        modelRouteRef: '',
        model: '',
        deliveryRef: '',
        deliveryReceiptSha256: '',
        latestDeliveredFrameAgeMs: null,
        aggregateSequence: 0,
        gaps: [reason],
        currentDeliveredFrame: false,
        routeMatches: false,
        modelMatches: false,
        selectedModelMatches: false,
        nonstaleDelivery: false,
      );
  factory StudioBodyBinding.fromLiveScreen(Object? sharing,
      {Object? rowanHost, DateTime? now}) {
    if (sharing == null) return StudioBodyBinding.none();
    if (sharing is! LiveScreenSharing) {
      return StudioBodyBinding.none(
          'Live Screen binding requires typed shell state');
    }
    if (rowanHost != null && rowanHost is! RowanWalkthroughOperationHost) {
      return StudioBodyBinding.none('Rowan binding requires typed model state');
    }
    final host = rowanHost as RowanWalkthroughOperationHost?;
    return StudioBodyBinding._fromEvidence(
      hasShellSession: sharing.hasSession,
      sessionRef: sharing.bodySessionRef,
      instrumentRef: 'screen',
      captureSessionRef: sharing.sessionId,
      viewedSourceRef: sharing.feed.viewedSource,
      boundRouteRef: sharing.boundDestination,
      boundModel: sharing.boundModel,
      selectedModel: host?.selectedModel,
      currentEndpointRef: host?.endpoint,
      frame: sharing.feed.deliveredFrame,
      delivery: sharing.feed.delivery,
      now: now,
    );
  }
  @visibleForTesting
  factory StudioBodyBinding.fromFrameDelivery({
    required String? sessionRef,
    String instrumentRef = 'screen',
    required String? captureSessionRef,
    String? viewedSourceRef,
    required String? boundRouteRef,
    required String? boundModel,
    required String? selectedModel,
    String? currentEndpointRef,
    required LiveScreenFrame? frame,
    required LiveScreenDelivery? delivery,
    DateTime? now,
    bool hasShellSession = true,
  }) =>
      StudioBodyBinding._fromEvidence(
        hasShellSession: hasShellSession,
        sessionRef: sessionRef,
        instrumentRef: instrumentRef,
        captureSessionRef: captureSessionRef,
        viewedSourceRef: viewedSourceRef,
        boundRouteRef: boundRouteRef,
        boundModel: boundModel,
        selectedModel: selectedModel,
        currentEndpointRef: currentEndpointRef,
        frame: frame,
        delivery: delivery,
        now: now,
      );
  factory StudioBodyBinding._fromEvidence({
    required bool hasShellSession,
    required String? sessionRef,
    required String instrumentRef,
    required String? captureSessionRef,
    required String? viewedSourceRef,
    required String? boundRouteRef,
    required String? boundModel,
    required String? selectedModel,
    String? currentEndpointRef,
    required LiveScreenFrame? frame,
    required LiveScreenDelivery? delivery,
    DateTime? now,
  }) {
    final gaps = <String>[];
    final safeSession = studioBodyText(sessionRef);
    final safeInstrument = studioBodyText(instrumentRef);
    final safeCapture = studioBodyText(captureSessionRef);
    final safeViewedSource = studioBodyText(viewedSourceRef);
    final safeRoute = studioBodyText(boundRouteRef);
    final safeBoundModel = studioBodyText(boundModel);
    final safeSelectedModel = studioBodyText(selectedModel);
    final safeCurrentEndpoint = studioBodyText(currentEndpointRef);
    final hasSession = hasShellSession &&
        safeSession.isNotEmpty &&
        safeInstrument.isNotEmpty &&
        safeCapture.isNotEmpty;
    if (!hasSession) gaps.add('No current Live Screen session is bound');
    final currentFrame = hasSession &&
        frame != null &&
        delivery != null &&
        frame.valid &&
        delivery.valid &&
        delivery.matches(frame) &&
        frame.sessionId == safeCapture &&
        (safeViewedSource.isEmpty || frame.sourceId == safeViewedSource);
    if (!currentFrame) {
      gaps.add('No current delivered Live Screen frame matches the session');
    }
    final effectiveAge =
        currentFrame ? delivery.ageAt((now ?? DateTime.now()).toUtc()) : null;
    if (currentFrame && effectiveAge == null) {
      gaps.add('Live Screen delivery age is unavailable');
    }
    final withinFreshnessLimit = effectiveAge != null &&
        effectiveAge <= studioBodyActionDeliveryFreshnessLimit;
    final nonstale = currentFrame &&
        !delivery.stale &&
        effectiveAge != null &&
        withinFreshnessLimit;
    if (currentFrame && !nonstale) {
      gaps.add(
          'Live Screen delivery is stale, expired, or has indeterminate age');
    }
    final routeMatches = currentFrame &&
        safeRoute.isNotEmpty &&
        delivery.modelRoute == safeRoute &&
        (safeCurrentEndpoint.isEmpty || safeCurrentEndpoint == safeRoute);
    if (!routeMatches) gaps.add('Live Screen route no longer matches frame');
    final modelMatches = currentFrame &&
        safeBoundModel.isNotEmpty &&
        delivery.model == safeBoundModel;
    if (!modelMatches) gaps.add('Live Screen model no longer matches frame');
    final selectedMatches = currentFrame &&
        safeSelectedModel.isNotEmpty &&
        delivery.model == safeSelectedModel;
    if (!selectedMatches) {
      gaps.add('Rowan selected model no longer matches delivered frame');
    }

    final deliveryRef = currentFrame && delivery.hasDeliveryReceiptRef
        ? delivery.deliveryRef
        : '';
    final deliveryReceipt = currentFrame && delivery.hasDeliveryReceiptRef
        ? delivery.deliveryReceiptSha256
        : '';
    if (currentFrame && (deliveryRef.isEmpty || deliveryReceipt.isEmpty)) {
      gaps.add('Delivery receipt refs unavailable from current Live Screen');
    }

    final source = currentFrame ? frame.sourceId : '';
    final sequence = currentFrame ? frame.sequence : 0;
    return StudioBodyBinding._(
      sessionRef: hasSession ? safeSession : '',
      instrumentRef: hasSession ? safeInstrument : '',
      captureSessionRef: currentFrame ? safeCapture : '',
      sourceRef: source,
      latestFrameRef: currentFrame ? '$source:$sequence' : '',
      frameSha256: currentFrame ? frame.digest : '',
      modelRouteRef: routeMatches ? safeRoute : '',
      model: modelMatches && selectedMatches ? safeBoundModel : '',
      deliveryRef: deliveryRef,
      deliveryReceiptSha256: deliveryReceipt,
      latestDeliveredFrameAgeMs: effectiveAge?.inMilliseconds,
      aggregateSequence: currentFrame ? frame.aggregateSequence : 0,
      gaps: List.unmodifiable(gaps),
      currentDeliveredFrame: currentFrame,
      routeMatches: routeMatches,
      modelMatches: modelMatches,
      selectedModelMatches: selectedMatches,
      nonstaleDelivery: nonstale,
    );
  }

  int get _frameSequence => int.tryParse(latestFrameRef.split(':').last) ?? 0;
  bool get hasCurrentSession =>
      sessionRef.isNotEmpty && instrumentRef.isNotEmpty;
  bool get deliveryReceiptRefsExposed =>
      deliveryRef.isNotEmpty && deliveryReceiptSha256.isNotEmpty;
  bool get canReadSnapshot =>
      hasCurrentSession &&
      _currentDeliveredFrame &&
      captureSessionRef.isNotEmpty &&
      sourceRef.isNotEmpty &&
      latestFrameRef.isNotEmpty &&
      frameSha256.isNotEmpty;
  bool get canSubmitStep =>
      canReadSnapshot &&
      _routeMatches &&
      _modelMatches &&
      _selectedModelMatches &&
      _nonstaleDelivery &&
      deliveryReceiptRefsExposed;
  String get blocker =>
      gaps.isEmpty ? 'Live Screen binding unavailable' : gaps.first;
  String get identityKey => [
        sessionRef,
        instrumentRef,
        captureSessionRef,
        sourceRef,
        latestFrameRef,
        frameSha256,
        modelRouteRef,
        model,
        deliveryRef,
        deliveryReceiptSha256,
        aggregateSequence.toString(),
        _currentDeliveredFrame.toString(),
        _routeMatches.toString(),
        _modelMatches.toString(),
        _selectedModelMatches.toString(),
        _nonstaleDelivery.toString(),
        gaps.join('|'),
      ].join('\u001f');

  /// Advancing frames may retain historical output; changing its principal may not.
  String get actionContextKey => [
        sessionRef,
        captureSessionRef,
        sourceRef,
        modelRouteRef,
        model,
        _routeMatches,
        _modelMatches,
        _selectedModelMatches,
      ].join('\u001f');

  Map<String, dynamic>? get modelDelivery {
    if (!canSubmitStep) return null;
    return {
      'parts': [
        {
          'kind': 'screen_frame',
          'frame': {
            'session_id': captureSessionRef,
            'source_id': sourceRef,
            'source_sequence': _frameSequence,
            'aggregate_sequence': aggregateSequence,
            'frame_sha256': frameSha256,
          },
          'model_route': modelRouteRef,
          'model': model,
          'delivery_ref': deliveryRef,
          'delivery_receipt_sha256': deliveryReceiptSha256,
        }
      ]
    };
  }
}
