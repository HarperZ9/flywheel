import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/live_screen_models.dart';
import 'package:flywheel_desktop/models/studio_body_models.dart';

void main() {
  test('status keeps missing authority and exact route pointers visible', () {
    final status = StudioBodyStatus.fromJson({
      'schema': 'flywheel.studio.body.status/v1',
      'body_contract_version': studioBodyContractVersion,
      'backend_ready': false,
      'unavailable_reason': 'authority_unconfigured',
      'available_effectors': [],
      'built': {
        'routes': true,
        'snapshot_contract': true,
        'sound_effector': true,
        'engine_visual_effector': true,
        'live_screen_preview_gateway': true,
      },
      'verified': {'usable_grant': false, 'status': 'authority_unconfigured'},
      'delivery_modes': ['deterministic_text_controls', 'image_frame_refs'],
      'authority': {
        'mode': 'accountable_surface_remote_durable',
        'configured': false,
        'available': true,
        'grant_required': true,
        'grant_verified': false,
        'required_env': [
          'ACCOUNTABLE_SURFACE_GRANTS',
          'ACCOUNTABLE_SURFACE_AUTHORITY_STATE',
        ],
      },
      'screen_feed': {
        'capture_session_ref': null,
        'preview_available': false,
        'native_video': 'unavailable_from_body_route',
        'latest_frame_ref': null,
        'latest_delivered_frame_age_ms': null,
      },
      'routes': {
        'status': '/api/studio/body/status',
        'snapshot': '/api/studio/body/snapshot',
        'step': '/api/studio/body/step',
        'live_screen_preview':
            '/api/live-screen/sessions/{session}/sources/{source}/frames/{sequence}/preview',
      },
    });

    expect(status.backendReady, isFalse);
    expect(status.canAttemptStep, isFalse);
    expect(status.authority.mode, 'accountable_surface_remote_durable');
    expect(
        status.authority.requiredEnv, contains('ACCOUNTABLE_SURFACE_GRANTS'));
    expect(status.built.engineVisualEffector, isTrue);
    expect(status.routes.step, '/api/studio/body/step');
    expect(status.screenFeed.nativeVideo, 'unavailable_from_body_route');
  });

  test('snapshot separates requested frame refs from validated evidence', () {
    final snapshot = StudioBodySnapshot.fromJson({
      'schema': 'flywheel.studio.body.snapshot/v1',
      'snapshot': {
        'snapshot_id': 'snap-1',
        'captured_at': '2026-09-15T12:00:00Z',
        'session_ref': 'session-1',
        'instrument_ref': 'instrument-1',
        'target': 'flywheel://studio/sound/session-1/instrument-1',
        'capture_session_ref': null,
        'latest_frame_ref': null,
        'latest_delivered_frame_age_ms': null,
        'capture': {
          'available': false,
          'validated': false,
          'status': 'capture_manager_unavailable',
          'source_ref': 'display:primary',
          'frame_sha256': 'a' * 64,
        },
        'requested_capture': {
          'latest_frame_ref': 'display:primary:7',
          'validated': false,
        },
        'observations': [
          {
            'observation_ref': 'obs-sound-seed',
            'source': 'flywheel.sound_studio.compose_state/v1',
            'delivery_mode': 'measured_text_json',
            'state_sha256': 'a' * 64,
            'latest_frame_ref': null,
          }
        ],
      },
    });

    expect(snapshot.primaryObservation?.observationRef, 'obs-sound-seed');
    expect(snapshot.latestFrameRef, isEmpty);
    expect(snapshot.requestedLatestFrameRef, 'display:primary:7');
    expect(snapshot.captureValidated, isFalse);
    expect(snapshot.captureStatus, 'capture_manager_unavailable');
    expect(snapshot.sourceRef, 'display:primary');
    expect(snapshot.frameSha256, 'a' * 64);
  });

  test('denied body step keeps authority receipt without claiming delivery',
      () {
    final result = StudioBodyStepResult.fromJson({
      'schema': 'flywheel.studio.body.step-response/v1',
      'accepted': false,
      'status': 'deny',
      'action_kind': studioBodySoundActionKind,
      'target': 'flywheel://studio/sound/session-1/instrument-1',
      'receipt': null,
      'authority_receipt': {
        'decision': 'deny',
        'acted': false,
        'verified': false,
        'authority_state': {'usage_counted': 0},
      },
      'errors': ['grant not found'],
    });

    expect(result.accepted, isFalse);
    expect(result.verifiedDelivery, isFalse);
    expect(result.authorityDecision, 'deny');
    expect(result.errors, contains('grant not found'));
    expect(jsonEncode(result.authorityReceipt), contains('usage_counted'));
  });

  test('live binding can read but cannot submit without receipt refs', () {
    final binding = _binding(withRefs: false);

    expect(binding.canReadSnapshot, isTrue);
    expect(binding.canSubmitStep, isFalse);
    expect(binding.modelDelivery, isNull);
    expect(binding.deliveryReceiptRefsExposed, isFalse);
    expect(binding.latestFrameRef, 'display:primary:7');
    expect(binding.gaps.join(' '), contains('Delivery receipt refs'));
  });

  test('live binding submits only exact nonstale route and selected model', () {
    final binding = _binding(withRefs: true);
    final part = binding.modelDelivery?['parts'][0] as Map<String, dynamic>?;

    expect(binding.canReadSnapshot, isTrue);
    expect(binding.canSubmitStep, isTrue);
    expect(binding.deliveryReceiptRefsExposed, isTrue);
    expect(binding.latestDeliveredFrameAgeMs, 1033);
    expect(part?['kind'], 'screen_frame');
    expect(part?['model_route'], 'openai_responses:vision');
    expect(part?['model'], 'gpt-5.6-sol');
    expect(part?['delivery_ref'], 'dlv_${'1' * 32}');
    expect(part?['delivery_receipt_sha256'], 'b' * 64);
    expect((part?['frame'] as Map)['source_sequence'], 7);
  });

  test('binding identity stays stable while age ticks below freshness limit',
      () {
    final first = _binding(withRefs: true);
    final later = _binding(
      withRefs: true,
      now: _deliveredAt.add(const Duration(seconds: 60)),
    );

    expect(first.latestDeliveredFrameAgeMs,
        isNot(later.latestDeliveredFrameAgeMs));
    expect(first.canSubmitStep, isTrue);
    expect(later.canSubmitStep, isTrue);
    expect(first.identityKey, later.identityKey);
  });

  test('binding identity changes when delivery freshness cutoff is crossed',
      () {
    final atCutoff = _binding(
      withRefs: true,
      now: _deliveredAt.add(studioBodyActionDeliveryFreshnessLimit -
          const Duration(milliseconds: 33)),
    );
    final expired = _binding(
      withRefs: true,
      now: _deliveredAt.add(studioBodyActionDeliveryFreshnessLimit -
          const Duration(milliseconds: 32)),
    );

    expect(atCutoff.latestDeliveredFrameAgeMs,
        studioBodyActionDeliveryFreshnessLimit.inMilliseconds);
    expect(expired.latestDeliveredFrameAgeMs,
        studioBodyActionDeliveryFreshnessLimit.inMilliseconds + 1);
    expect(atCutoff.canReadSnapshot, isTrue);
    expect(expired.canReadSnapshot, isTrue);
    expect(atCutoff.canSubmitStep, isTrue);
    expect(expired.canSubmitStep, isFalse);
    expect(atCutoff.identityKey, isNot(expired.identityKey));
  });

  test('stale or mismatched Rowan route keeps read-only snapshot access', () {
    for (final binding in [
      _binding(withRefs: true, stale: true),
      _binding(withRefs: true, boundRoute: 'other-route'),
      _binding(withRefs: true, currentEndpoint: 'other-route'),
      _binding(withRefs: true, boundModel: 'other-model'),
      _binding(withRefs: true, selectedModel: 'other-model'),
    ]) {
      expect(binding.canReadSnapshot, isTrue);
      expect(binding.canSubmitStep, isFalse);
      expect(binding.modelDelivery, isNull);
    }
  });

  test('mismatched frame delivery cannot read or submit', () {
    final binding = _binding(withRefs: true, frameDigest: 'c' * 64);

    expect(binding.canReadSnapshot, isFalse);
    expect(binding.canSubmitStep, isFalse);
    expect(binding.latestFrameRef, isEmpty);
    expect(binding.modelDelivery, isNull);
  });

  test('legacy untyped binding surface refuses duck-typed state', () {
    final binding = StudioBodyBinding.fromLiveScreen(Object());

    expect(binding.canReadSnapshot, isFalse);
    expect(binding.canSubmitStep, isFalse);
    expect(binding.blocker, contains('typed shell state'));
  });
}

final _capturedAt = DateTime.utc(2026, 9, 15, 10);
final _deliveredAt = _capturedAt.add(const Duration(seconds: 1));

StudioBodyBinding _binding({
  required bool withRefs,
  bool stale = false,
  String boundRoute = 'openai_responses:vision',
  String boundModel = 'gpt-5.6-sol',
  String selectedModel = 'gpt-5.6-sol',
  String? currentEndpoint,
  String frameDigest = '',
  DateTime? now,
}) {
  final frame = _frame(frameDigest.isEmpty ? 'a' * 64 : frameDigest);
  final delivery = _delivery(withRefs: withRefs, stale: stale);
  return StudioBodyBinding.fromFrameDelivery(
    sessionRef: 'studio-screen-1',
    captureSessionRef: 'cap-1',
    viewedSourceRef: 'display:primary',
    boundRouteRef: boundRoute,
    boundModel: boundModel,
    selectedModel: selectedModel,
    currentEndpointRef: currentEndpoint ?? boundRoute,
    frame: frame,
    delivery: delivery,
    now: now ?? _deliveredAt.add(const Duration(seconds: 1)),
  );
}

LiveScreenFrame _frame(String digest) => LiveScreenFrame.fromJson({
      'session_id': 'cap-1',
      'source_id': 'display:primary',
      'source_sequence': 7,
      'aggregate_sequence': 11,
      'captured_at_utc': _capturedAt.toIso8601String(),
      'frame_sha256': digest,
      'width': 1920,
      'height': 1080,
    });

LiveScreenDelivery _delivery({required bool withRefs, required bool stale}) {
  final json = <String, Object?>{
    'session_id': 'cap-1',
    'source_id': 'display:primary',
    'source_sequence': 7,
    'aggregate_sequence': 11,
    'frame': {
      'session_id': 'cap-1',
      'source_id': 'display:primary',
      'source_sequence': 7,
      'aggregate_sequence': 11,
      'frame_sha256': 'a' * 64,
    },
    'frame_sha256': 'a' * 64,
    'model_route': 'openai_responses:vision',
    'model': 'gpt-5.6-sol',
    'delivery_mode': 'sampled_image',
    'delivered_at_utc': _deliveredAt.toIso8601String(),
    'frame_age_ms': 33,
    'stale': stale,
  };
  if (withRefs) {
    json['delivery_ref'] = 'dlv_${'1' * 32}';
    json['delivery_receipt_sha256'] = 'b' * 64;
  }
  return LiveScreenDelivery.fromJson(json);
}
