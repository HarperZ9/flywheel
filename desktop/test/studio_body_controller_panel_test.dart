import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/studio_body_client.dart';
import 'package:flywheel_desktop/controllers/studio_body_controller.dart';
import 'package:flywheel_desktop/models/studio_body_models.dart';
import 'package:flywheel_desktop/models/live_screen_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/studio_body_panel.dart';
void main() {
  test('completed output survives next frame but not a model-context change',
      () async {
    final api = _FakeStudioBodyApi()..nextStatus = _status(configured: true);
    final controller = StudioBodyController(api)..updateBinding(_binding());
    await controller.refreshStatus();
    await controller.refreshSnapshot();
    await controller.submitStep();
    final result = controller.lastResult;
    expect(result, isNotNull);
    controller.updateBinding(_binding(sequence: 8));
    expect(controller.snapshot, isNull);
    expect(controller.lastResult, same(result));
    controller.updateBinding(StudioBodyBinding.none());
    expect(controller.lastResult, isNull);
    controller.dispose();
  });
  test('controller requires live delivery binding before snapshot or step',
      () async {
    final api = _FakeStudioBodyApi()..nextStatus = _status(configured: true);
    final controller = StudioBodyController(api, idFactory: _fixedIds());
    await controller.refreshStatus();
    await controller.refreshSnapshot();
    expect(api.snapshotCalls, 0);
    expect(controller.error, contains('Live Screen'));
    controller.updateBinding(_binding());
    await controller.refreshSnapshot();
    expect(api.snapshotCalls, 1);
    expect(api.lastSnapshotRequest?.sessionRef, 'studio-screen-1');
    expect(api.lastSnapshotRequest?.instrumentRef, 'screen');
    expect(api.lastSnapshotRequest?.sourceRef, 'display:primary');
    expect(api.lastSnapshotRequest?.latestFrameRef, 'display:primary:7');
    expect(controller.canSubmitStep, isTrue);
    await controller.submitStep();
    expect(api.stepCalls, 1);
    expect(api.lastDraft?.modelRouteRef, 'openai_responses:vision');
    expect(api.lastDraft?.target,
        'flywheel://studio/sound/studio-screen-1/screen');
    final part = api.lastDraft?.modelDelivery?['parts'][0];
    expect(part['kind'], 'screen_frame');
    expect(part['frame']['frame_sha256'], _sha('a'));
    api.unboundObservation = true;
    await controller.refreshSnapshot();
    expect(controller.canSubmitStep, isFalse);
    await controller.submitStep();
    expect(api.stepCalls, 1);
  });
  test('instrument and binding changes invalidate dependent evidence',
      () async {
    final api = _FakeStudioBodyApi()..nextStatus = _status(configured: true);
    final controller = StudioBodyController(api, idFactory: _fixedIds());
    controller.updateBinding(_binding());
    await controller.refreshStatus();
    await controller.refreshSnapshot();
    await controller.submitStep();
    expect(controller.snapshot, isNotNull);
    expect(controller.lastResult, isNotNull);

    controller.updateBinding(_binding(source: 'display:secondary'));
    expect(controller.snapshot, isNull);
    expect(controller.lastResult, isNull);

    await controller.refreshSnapshot();
    expect(controller.snapshot, isNotNull);
    controller.setInstrument(StudioBodyInstrument.engine);
    expect(controller.snapshot, isNull);
    expect(controller.lastResult, isNull);
  });

  test('requests serialize and stale disposed replies are ignored', () async {
    final snapshotCompleter = Completer<StudioBodySnapshot>();
    final api = _FakeStudioBodyApi()
      ..nextStatus = _status(configured: true)
      ..snapshotCompleter = snapshotCompleter;
    final controller = StudioBodyController(api, idFactory: _fixedIds())
      ..updateBinding(_binding());
    await controller.refreshStatus();

    final first = controller.refreshSnapshot();
    await Future<void>.delayed(Duration.zero);
    await controller.refreshSnapshot();
    await controller.submitStep();
    expect(api.snapshotCalls, 1);
    expect(api.stepCalls, 0);

    controller.dispose();
    snapshotCompleter.complete(_snapshot());
    await first;
  });

  testWidgets('panel binds from live sharing and removes manual route entry',
      (tester) async {
    tester.view.physicalSize = const Size(390, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final controller = StudioBodyController(
      _FakeStudioBodyApi()..nextStatus = _status(configured: false),
      idFactory: _fixedIds(),
    );

    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
          body: SingleChildScrollView(
              child: StudioBodyPanel(controller: controller))),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('studio-body-model-route-ref')),
        findsNothing);
    expect(find.textContaining('authority is not configured'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('panel gives clear no-current-session state', (tester) async {
    final controller = StudioBodyController(_FakeStudioBodyApi());
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
          body: SingleChildScrollView(
              child: StudioBodyPanel(controller: controller))),
    ));
    await tester.pumpAndSettle();

    expect(
        find.textContaining('No current Live Screen session'), findsOneWidget);
    final action = tester.widget<FilledButton>(
        find.byKey(const ValueKey('studio-body-submit-step')));
    expect(action.onPressed, isNull);
  });
}

class _FakeStudioBodyApi implements StudioBodyApi {
  bool unboundObservation = false;
  StudioBodyStatus? nextStatus;
  Completer<StudioBodySnapshot>? snapshotCompleter;
  int snapshotCalls = 0, stepCalls = 0;
  StudioBodySnapshotRequest? lastSnapshotRequest;
  StudioBodyStepDraft? lastDraft;

  @override
  Future<StudioBodyStatus> status() async =>
      nextStatus ?? _status(configured: false);

  @override
  Future<StudioBodySnapshot> snapshot(StudioBodySnapshotRequest request) async {
    snapshotCalls++;
    lastSnapshotRequest = request;
    final pending = snapshotCompleter;
    if (pending != null) return pending.future;
    return _snapshot(unboundObservation: unboundObservation);
  }

  @override
  Future<StudioBodyStepResult> submitStep(StudioBodyStepDraft draft) async {
    stepCalls++;
    lastDraft = draft;
    return StudioBodyStepResult.fromJson({
      'schema': 'flywheel.studio.body.step-response/v1',
      'accepted': false,
      'status': 'denied',
      'action_kind': draft.actionKind,
      'target': draft.target,
      'receipt': null,
      'authority_receipt': {
        'decision': 'deny',
        'acted': false,
        'verified': false
      },
      'errors': ['outside grant'],
    });
  }
}

String Function() _fixedIds() {
  var i = 0;
  return () => i.isEven ? 'client-${++i}' : 'idem-${++i}';
}

StudioBodyBinding _binding(
    {String source = 'display:primary', int sequence = 7}) {
  final now = DateTime.utc(2026, 9, 15, 12);
  final identity = <String, dynamic>{
    'session_id': 'cap-1',
    'source_id': source,
    'source_sequence': sequence,
    'aggregate_sequence': sequence + 4,
    'frame_sha256': _sha('a'),
  };
  return StudioBodyBinding.fromFrameDelivery(
    sessionRef: 'studio-screen-1',
    captureSessionRef: 'cap-1',
    boundRouteRef: 'openai_responses:vision',
    boundModel: 'gpt-5.6-sol',
    selectedModel: 'gpt-5.6-sol',
    viewedSourceRef: source,
    now: now,
    frame: LiveScreenFrame.fromJson({
      ...identity,
      'captured_at_utc': now.toIso8601String(),
      'width': 1920,
      'height': 1080
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
      'delivery_receipt_sha256': _sha('b')
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
        'required_env': [
          'ACCOUNTABLE_SURFACE_GRANTS',
          'ACCOUNTABLE_SURFACE_AUTHORITY_STATE'
        ],
      },
      'screen_feed': {'native_video': 'unavailable_from_body_route'},
      'routes': {
        'step': '/api/studio/body/step',
        'snapshot': '/api/studio/body/snapshot'
      },
    });

StudioBodySnapshot _snapshot({bool unboundObservation = false}) =>
    StudioBodySnapshot.fromJson({
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
          'frame_sha256': _sha('a')
        },
        'requested_capture': {
          'validated': true,
          'latest_frame_ref': 'display:primary:7'
        },
        'observations': [
          {
            'observation_ref': 'obs-sound',
            'source': 'flywheel.sound_studio.compose_state/v1',
            'delivery_mode': 'measured_text_json',
            'state_sha256': _sha('c'),
            'latest_frame_ref':
                unboundObservation ? 'display:primary:6' : 'display:primary:7',
          }
        ],
      },
    });

String _sha(String char) => List.filled(64, char).join();
