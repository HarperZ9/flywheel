import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:integration_test/integration_test.dart';

import 'package:flywheel_desktop/assistant/rowan_action_cue_caption.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_clip_model.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_controller.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_models.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_strip.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_widget.dart';
import 'package:flywheel_desktop/client/gateway_auth.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'package:flywheel_desktop/client/journey_api.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/live_screen_sharing.dart';
import 'package:flywheel_desktop/controllers/rowan_operation_controller.dart';
import 'package:flywheel_desktop/controllers/rowan_operation_host_adapter.dart';
import 'package:flywheel_desktop/models/evidence_state.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/services/connection_config.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';
import 'package:flywheel_desktop/shell/shell_rowan_cues.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';

part 'android_rowan_cue_acceptance_helpers.dart';
part 'android_rowan_cue_acceptance_receipts.dart';
part 'android_rowan_cue_acceptance_surface.dart';

const _phase = String.fromEnvironment('FLYWHEEL_ANDROID_ROWAN_CUE_PHASE');
const _runId = String.fromEnvironment('FLYWHEEL_ANDROID_ROWAN_CUE_RUN_ID');
const _prefix = 'FLYWHEEL_ANDROID_ROWAN_CUE_RECEIPT_JSON:';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets(
    'Android Rowan cue physical acceptance $_phase',
    skip: !Platform.isAndroid,
    (tester) async {
      await initFlywheelHome();
      final config = ConnectionStore().load();
      final token = config.token;
      if (token == null || token.isEmpty) {
        throw StateError('paired gateway token missing');
      }
      final clientHttp = http.Client();
      addTearDown(clientHttp.close);
      final client = GatewayClient(
        baseUrl: config.effectiveBaseUrl,
        httpClient: AuthedClient(clientHttp, readToken: config.tokenSource),
      );
      if (_phase == 'start') {
        await _startPhase(tester, client, config, token);
      } else if (_phase == 'recover') {
        await _recoverPhase(tester, client, config, token);
      } else {
        throw StateError('unknown Rowan cue phase: $_phase');
      }
    },
  );
}

Future<void> _startPhase(
  WidgetTester tester,
  GatewayClient client,
  ConnectionConfig config,
  String token,
) async {
  final auth = await _authControls(config.effectiveBaseUrl, token);
  expect(auth['missing_token_ok'], isFalse);
  expect(auth['wrong_token_ok'], isFalse);
  expect(await client.isAlive(), isTrue);
  final world = await client.projectedWorld();
  if (world.rootHash.isEmpty) throw StateError('world root missing');

  final journeyApi = GatewayJourneyApi(client);
  final createId =
      'android-rowan-cue-journey-${DateTime.now().microsecondsSinceEpoch}';
  final proposal = await journeyApi.prepareGrant(GrantIntent.create(
    goal: 'Android Rowan cue acceptance',
    intakeRef: 'android-rowan-cue-intake.json',
    clientRequestId: createId,
  ));
  if (proposal.invalidResponse) throw StateError('invalid Journey proposal');
  final grant = await journeyApi.approveGrantOnce(proposal.proposalRef);
  if (grant.invalidResponse || grant.grantRef != proposal.plannedGrantRef) {
    throw StateError('invalid Journey grant');
  }
  final ack = await journeyApi.create(JourneyCreateRequest(
    goal: 'Android Rowan cue acceptance',
    intakeRef: 'android-rowan-cue-intake.json',
    clientRequestId: createId,
    grantRef: grant.grantRef,
  ));
  if (ack.invalidResponse) throw StateError('invalid Journey ack');

  final store = JourneySessionStore()
    ..save(
      JourneySession(journeyRef: ack.journeyRef, lens: JourneyLens.verify),
    );
  final grants = GatewayOperationController(GatewayGrantClient(client));
  final mount = await _mountHarness(
    tester,
    client: client,
    store: store,
    binding: GatewayJourneyBinding(ack.journeyRef, ack.eventHeadSha256),
    grants: grants,
  );
  addTearDown(grants.dispose);
  addTearDown(mount.dispose);

  final controlState = await _openControlsAndOptIn(tester, mount.cues);
  final nativeCompletionFuture = _waitForNativePlayerCompletion(mount.cues);
  final started = await tester.runAsync(() async => mount.rowan.start(
        mount.context,
        'Android Rowan cue acceptance run ${_runIdValue()}',
      ));
  expect(started?.value, isTrue,
      reason:
          'Authorization: ${started?.failure?.code}; grant: ${grants.failure?.code}');

  final firstCue = await tester.runAsync(
    () => _waitForOperationTelemetry(mount.cues, minCount: 1),
  );
  final nativeCompletion = await tester.runAsync(() => nativeCompletionFuture);
  expect(nativeCompletion?['native_player_completion_observed'], isTrue);
  await tester.pumpAndSettle();
  final caption = mount.cues.controller.captions.value;
  expect(caption, isNotNull);
  expect(find.byKey(const Key('rowan-cue-caption-strip')), findsOneWidget);
  expect(find.textContaining('Recorded cue:'), findsWidgets);

  final duplicateOrCooldown = await tester.runAsync(
    () => _exerciseDuplicateOrCooldown(mount.cues, mount.rowan),
  );
  expect(duplicateOrCooldown?['ok'], isTrue);

  final muteState = await _toggleMuteAndExerciseSuppression(
    tester,
    mount.cues,
    mount.rowan,
  );
  expect(muteState['muted_after_toggle'], isTrue);
  expect(muteState['muted_decision_reason'], 'muted');

  final requestSha = await _waitForRequestSha(store);
  final operations =
      await _matchingOperations(client, ack.journeyRef, requestSha);
  final detachClean = await mount.rowan.operationState.detachObservation();

  _emit(
    _receipt('start', config, token, {
      'world_ok': true,
      'world_root_hash': world.rootHash,
      'auth_controls': auth,
      'journey_ref': ack.journeyRef,
      'journey_event_head_sha256': ack.eventHeadSha256,
      'proposal_ref': proposal.proposalRef,
      'grant_ref': grant.grantRef,
      'request_sha256': requestSha,
      'observation_detach_clean': detachClean,
      'rowan_controls': controlState,
      'operation_cue': {
        'first_operation_telemetry': firstCue?.toJson(),
        'caption': _captionJson(caption),
        'caption_strip_visible': true,
        'telemetry_count': mount.cues.controller.telemetry.length,
        'duplicate_or_cooldown': duplicateOrCooldown,
      },
      'mute': muteState,
      'native_playback':
          _nativePlaybackFacts(mount.cues, firstCue, nativeCompletion),
      ...operations,
    }),
    token,
  );
}

Future<void> _recoverPhase(
  WidgetTester tester,
  GatewayClient client,
  ConnectionConfig config,
  String token,
) async {
  final store = JourneySessionStore();
  final session = store.load();
  if (session == null || session.operationRequestSha256 == null) {
    throw StateError('stored Journey request hash missing');
  }
  final grants = GatewayOperationController(GatewayGrantClient(client));
  final mount = await _mountHarness(
    tester,
    client: client,
    store: store,
    binding: GatewayJourneyBinding(
      session.journeyRef,
      session.operationEventHeadSha256 ?? session.operationRequestSha256!,
    ),
    grants: grants,
  );
  addTearDown(grants.dispose);
  addTearDown(mount.dispose);

  final controlState = await _openControlsAndOptIn(tester, mount.cues);
  final recovered = await tester.runAsync(mount.rowan.recoverFromSession);
  await tester.runAsync(() => Future<void>.delayed(
        const Duration(milliseconds: 750),
      ));
  await tester.pumpAndSettle();
  expect(recovered, isTrue);
  expect(mount.cues.controller.telemetry, isEmpty);
  expect(mount.cues.controller.captions.value, isNull);
  expect(find.byKey(const Key('rowan-cue-caption-strip')), findsNothing);

  final operations = await _matchingOperations(
    client,
    session.journeyRef,
    session.operationRequestSha256!,
    requireCompletedTerminal: true,
  );
  final terminalRef = operations['terminal_operation_ref'] as String?;
  if (terminalRef == null) throw StateError('terminal operation missing');
  final result = await GatewayOperations(client).result(terminalRef);
  final resultVerified = result.operationRef == terminalRef &&
      result.state == OperationState.completed;
  expect(resultVerified, isTrue);
  final detachClean = await mount.rowan.operationState.detachObservation();
  _emit(
    _receipt('recover', config, token, {
      'recover_from_session': recovered,
      'recovery_silent': true,
      'observation_detach_clean': detachClean,
      'journey_ref': session.journeyRef,
      'request_sha256': session.operationRequestSha256,
      'rowan_controls': controlState,
      'operation_cue': {
        'telemetry_count': mount.cues.controller.telemetry.length,
        'caption': _captionJson(mount.cues.controller.captions.value),
        'caption_strip_visible': false,
      },
      'native_playback': _nativePlaybackFacts(mount.cues, null, null),
      ...operations,
      'result': result.toJson(),
      'result_required': true,
      'result_verified': resultVerified,
      'result_state': result.toJson()['state'],
      'result_operation_ref': result.operationRef,
      'result_canonical_sha256': result.canonicalSha256,
    }),
    token,
  );
}
