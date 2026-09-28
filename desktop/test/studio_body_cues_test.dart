import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_controller.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_event_binding.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_models.dart';
import 'package:flywheel_desktop/client/studio_body_client.dart';
import 'package:flywheel_desktop/controllers/studio_body_controller.dart';
import 'package:flywheel_desktop/models/live_screen_models.dart';
import 'package:flywheel_desktop/models/studio_body_models.dart';

void main() {
  test('sound submit emits audio pass only after a real submit starts',
      () async {
    final api = _FakeStudioBodyApi()..nextStatus = _status(configured: true);
    final events = <RowanActionCueEvent>[];
    final controller = StudioBodyController(
      api,
      idFactory: _fixedIds(),
      dispatchCue: _capture(events),
    )..updateBinding(_binding());

    await controller.submitStep();
    expect(events, isEmpty);
    expect(api.stepCalls, 0);

    await controller.refreshStatus();
    await controller.refreshSnapshot();
    await controller.submitStep();

    expect(api.stepCalls, 1);
    expect(events.map((event) => event.kind.wire), ['studio.audio_pass']);
    controller.dispose();
  });

  test('visual submit emits visual pass and review only for verified result',
      () async {
    final events = <RowanActionCueEvent>[];
    final api = _FakeStudioBodyApi()
      ..nextStatus = _status(configured: true)
      ..verified = true;
    final controller = StudioBodyController(
      api,
      idFactory: _fixedIds(),
      dispatchCue: _capture(events),
    )..updateBinding(_binding());
    controller.setInstrument(StudioBodyInstrument.engine);

    await controller.refreshStatus();
    await controller.refreshSnapshot();
    await controller.submitStep();

    expect(api.stepCalls, 1);
    expect(events.map((event) => event.kind.wire),
        ['studio.visual_pass', 'studio.render_review']);
    controller.dispose();
  });

  test('visual denied result does not emit render review', () async {
    final events = <RowanActionCueEvent>[];
    final api = _FakeStudioBodyApi()..nextStatus = _status(configured: true);
    final controller = StudioBodyController(
      api,
      idFactory: _fixedIds(),
      dispatchCue: _capture(events),
    )..updateBinding(_binding());
    controller.setInstrument(StudioBodyInstrument.engine);

    await controller.refreshStatus();
    await controller.refreshSnapshot();
    await controller.submitStep();

    expect(api.stepCalls, 1);
    expect(events.map((event) => event.kind.wire), ['studio.visual_pass']);
    controller.dispose();
  });
}

RowanActionCueDispatch _capture(List<RowanActionCueEvent> events) =>
    (event) async {
      events.add(event);
      return const RowanActionCueDecision(
        outcome: RowanActionCueOutcome.suppressed,
        reason: RowanActionCueReason.optInDisabled,
      );
    };

class _FakeStudioBodyApi implements StudioBodyApi {
  StudioBodyStatus? nextStatus;
  bool verified = false;
  int snapshotCalls = 0, stepCalls = 0;

  @override
  Future<StudioBodyStatus> status() async =>
      nextStatus ?? _status(configured: false);

  @override
  Future<StudioBodySnapshot> snapshot(StudioBodySnapshotRequest request) async {
    snapshotCalls++;
    return _snapshot();
  }

  @override
  Future<StudioBodyStepResult> submitStep(StudioBodyStepDraft draft) async {
    stepCalls++;
    return StudioBodyStepResult.fromJson({
      'schema': 'flywheel.studio.body.step-response/v1',
      'accepted': verified,
      'status': verified ? 'accepted' : 'denied',
      'action_kind': draft.actionKind,
      'target': draft.target,
      'receipt': verified ? {'result_sha256': _sha('d')} : null,
      'authority_receipt': {
        'decision': verified ? 'allow' : 'deny',
        'acted': verified,
        'verified': verified,
      },
      'errors': verified ? [] : ['outside grant'],
    });
  }
}

String Function() _fixedIds() {
  var i = 0;
  return () => i.isEven ? 'client-${++i}' : 'idem-${++i}';
}

StudioBodyBinding _binding() {
  final now = DateTime.utc(2026, 9, 15, 12);
  final identity = <String, dynamic>{
    'session_id': 'cap-1',
    'source_id': 'display:primary',
    'source_sequence': 7,
    'aggregate_sequence': 11,
    'frame_sha256': _sha('a'),
  };
  return StudioBodyBinding.fromFrameDelivery(
    sessionRef: 'studio-screen-1',
    captureSessionRef: 'cap-1',
    boundRouteRef: 'openai_responses:vision',
    boundModel: 'gpt-5.6-sol',
    selectedModel: 'gpt-5.6-sol',
    viewedSourceRef: 'display:primary',
    now: now,
    frame: LiveScreenFrame.fromJson({
      ...identity,
      'captured_at_utc': now.toIso8601String(),
      'width': 1920,
      'height': 1080,
    }),
    delivery: LiveScreenDelivery.fromJson({
      ...identity,
      'frame': identity,
      'model_route': 'openai_responses:vision',
      'model': 'gpt-5.6-sol',
      'delivery_mode': 'sampled_image',
      'delivered_at_utc': now.toIso8601String(),
      'frame_age_ms': 33,
      'stale': false,
      'delivery_ref': 'dlv_${'1' * 32}',
      'delivery_receipt_sha256': _sha('b'),
    }),
  );
}

StudioBodyStatus _status({required bool configured}) =>
    StudioBodyStatus.fromJson({
      'schema': 'flywheel.studio.body.status/v1',
      'body_contract_version': studioBodyContractVersion,
      'backend_ready': configured,
      'unavailable_reason':
          configured ? 'deferred_until_step' : 'authority_unconfigured',
      'built': {
        'routes': true,
        'snapshot_contract': true,
        'sound_effector': true,
        'engine_visual_effector': true,
        'live_screen_preview_gateway': true,
      },
      'verified': {'usable_grant': false, 'status': 'deferred_until_step'},
      'delivery_modes': ['deterministic_text_controls', 'image_frame_refs'],
      'authority': {
        'mode': 'accountable_surface_remote_durable',
        'configured': configured,
        'available': true,
        'grant_required': true,
        'grant_verified': false,
      },
      'screen_feed': {'native_video': 'unavailable_from_body_route'},
      'routes': {
        'step': '/api/studio/body/step',
        'snapshot': '/api/studio/body/snapshot'
      },
    });

StudioBodySnapshot _snapshot() => StudioBodySnapshot.fromJson({
      'schema': 'flywheel.studio.body.snapshot/v1',
      'snapshot': {
        'snapshot_id': 'snap-1',
        'captured_at': '2026-09-15T12:00:00Z',
        'session_ref': 'studio-screen-1',
        'instrument_ref': 'screen',
        'target': 'flywheel://studio/sound/studio-screen-1/screen',
        'capture_session_ref': 'cap-1',
        'latest_frame_ref': 'display:primary:7',
        'latest_delivered_frame_age_ms': 33,
        'capture': {
          'available': true,
          'validated': true,
          'status': 'validated',
          'source_ref': 'display:primary',
          'frame_sha256': _sha('a'),
        },
        'observations': [
          {
            'observation_ref': 'obs-sound',
            'source': 'flywheel.sound_studio.compose_state/v1',
            'delivery_mode': 'measured_text_json',
            'state_sha256': _sha('c'),
            'latest_frame_ref': 'display:primary:7',
          }
        ],
      },
    });

String _sha(String char) => List.filled(64, char).join();
