import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:integration_test/integration_test.dart';
import 'package:flywheel_desktop/client/gateway_auth.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'package:flywheel_desktop/client/journey_api.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/rowan_operation_controller.dart';
import 'package:flywheel_desktop/models/evidence_state.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/services/connection_config.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
const _phase = String.fromEnvironment('FLYWHEEL_ANDROID_REAL_HANDOFF_PHASE');
const _runId = String.fromEnvironment('FLYWHEEL_ANDROID_REAL_HANDOFF_RUN_ID');
const _prefix = 'FLYWHEEL_ANDROID_REAL_GATEWAY_HANDOFF_RECEIPT_JSON:';
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('real Android gateway handoff $_phase', (tester) async {
    late BuildContext context;
    GatewayJourneyBinding? binding;
    GatewayOperationController? grants;
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: GatewayOperationScope(
        authorize: (_, operation, current, dispatch) {
          final activeBinding = binding;
          final activeGrants = grants;
          return activeBinding == null || activeGrants == null
              ? Future.value(const GatewayAuthorizationOutcome.failure(
                  GatewayOperationFailure(
                      'JOURNEY_REQUIRED', 'Journey binding missing'),
                ))
              : _authorize(
                  activeGrants, activeBinding, operation, current, dispatch);
        },
        child: Builder(builder: (ctx) {
          context = ctx;
          return const SizedBox.shrink();
        }),
      ),
    ));
    await tester.runAsync(() async {
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
        if (!context.mounted) throw StateError('test context unmounted');
        await _startPhase(context, client, config, token, (b, g) {
          binding = b;
          grants = g;
        });
      } else if (_phase == 'recover') {
        await _recoverPhase(client, config, token);
      } else {
        throw StateError('unknown real gateway handoff phase: $_phase');
      }
    });
  });
}
Future<void> _startPhase(
  BuildContext context,
  GatewayClient client,
  ConnectionConfig config,
  String token,
  void Function(GatewayJourneyBinding, GatewayOperationController)
      bindAuthorizer,
) async {
  final auth = await _authControls(config.effectiveBaseUrl, token);
  expect(auth['missing_token_ok'], isFalse);
  expect(auth['wrong_token_ok'], isFalse);
  expect(await client.isAlive(), isTrue);
  final world = await client.projectedWorld();
  if (world.rootHash.isEmpty) throw StateError('world root missing');
  final journeyApi = GatewayJourneyApi(client);
  final createId =
      'android-real-journey-${DateTime.now().microsecondsSinceEpoch}';
  final proposal = await journeyApi.prepareGrant(GrantIntent.create(
    goal: 'Android real gateway handoff acceptance',
    intakeRef: 'android-real-intake.json',
    clientRequestId: createId,
  ));
  if (proposal.invalidResponse) throw StateError('invalid Journey proposal');
  final grant = await journeyApi.approveGrantOnce(proposal.proposalRef);
  if (grant.invalidResponse || grant.grantRef != proposal.plannedGrantRef) {
    throw StateError('invalid Journey grant');
  }
  final ack = await journeyApi.create(JourneyCreateRequest(
    goal: 'Android real gateway handoff acceptance',
    intakeRef: 'android-real-intake.json',
    clientRequestId: createId,
    grantRef: grant.grantRef,
  ));
  if (ack.invalidResponse) throw StateError('invalid Journey ack');
  final store = JourneySessionStore()
    ..save(
        JourneySession(journeyRef: ack.journeyRef, lens: JourneyLens.verify));
  final binding = GatewayJourneyBinding(ack.journeyRef, ack.eventHeadSha256);
  final grants = GatewayOperationController(GatewayGrantClient(client));
  bindAuthorizer(binding, grants);
  final rowan = RowanOperationController(client, sessionStore: store)
    ..setEndpoint('stub')
    ..setMaxStepsOverride(1);
  addTearDown(grants.dispose);
  addTearDown(rowan.dispose);
  if (!context.mounted) throw StateError('test context unmounted');
  final started = await rowan.start(
    context,
    'Android real gateway handoff acceptance run ${_runIdValue()}',
  );
  expect(started.value, isTrue,
      reason: 'Authorization: ${started.failure?.code}; grant: ${grants.failure?.code}');
  final requestSha = await _waitForRequestSha(store);
  final operations =
      await _matchingOperations(client, ack.journeyRef, requestSha);
  final detachClean = await rowan.operationState.detachObservation();
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
        ...operations,
      }),
      token);
}
Future<void> _recoverPhase(
  GatewayClient client,
  ConnectionConfig config,
  String token,
) async {
  final store = JourneySessionStore();
  final session = store.load();
  if (session == null || session.operationRequestSha256 == null) {
    throw StateError('stored Journey request hash missing');
  }
  final rowan = RowanOperationController(client, sessionStore: store);
  addTearDown(rowan.dispose);
  final recovered = await rowan.recoverFromSession();
  final operations = await _matchingOperations(
    client,
    session.journeyRef,
    session.operationRequestSha256!,
  );
  OperationResult? result;
  final terminalRef = operations['terminal_operation_ref'] as String?;
  if (terminalRef != null) {
    result = await GatewayOperations(client).result(terminalRef);
  }
  final detachClean = await rowan.operationState.detachObservation();
  _emit(
      _receipt('recover', config, token, {
        'recover_from_session': recovered,
        'observation_detach_clean': detachClean,
        'journey_ref': session.journeyRef,
        'request_sha256': session.operationRequestSha256,
        ...operations,
        'result': result?.toJson(),
      }),
      token);
}
Future<Object?> _authorize(
  GatewayOperationController grants,
  GatewayJourneyBinding binding,
  GatewayOperation operation,
  GatewayOperationSupplier current,
  Future<Object?> Function(Map<String, dynamic>) dispatch,
) async {
  final prepared = await grants.prepare(
    operation,
    binding: binding,
    currentOperation: current,
    currentBinding: () => binding,
  );
  if (!prepared) {
    return GatewayAuthorizationOutcome.failure(
      grants.failure ??
          const GatewayOperationFailure(
              'PREPARE_FAILED', 'Grant prepare failed'),
    );
  }
  final value = await grants.approveAndDispatch(dispatch);
  return value == null
      ? const GatewayAuthorizationOutcome.denied()
      : GatewayAuthorizationOutcome.value(value);
}
Future<String> _waitForRequestSha(JourneySessionStore store) async {
  for (var i = 0; i < 80; i++) {
    final value = store.load()?.operationRequestSha256;
    if (value != null && value.isNotEmpty) return value;
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
  throw StateError('operation request hash was not stored');
}
Future<Map<String, Object?>> _matchingOperations(
  GatewayClient client,
  String journeyRef,
  String requestSha,
) async {
  for (var i = 0; i < 40; i++) {
    final page =
        await GatewayOperations(client).listByJourney(journeyRef, limit: 50);
    final matches = page.operations
        .where((item) =>
            page.requestSha256ByOperation[item.operationRef] == requestSha)
        .toList(growable: false);
    if (matches.isNotEmpty || i == 39) {
      return {
        'operation_count_for_request': matches.length,
        'operation_refs': matches.map((item) => item.operationRef).toList(),
        'operation_set': page.toJson(),
        'snapshot': matches.isEmpty ? null : matches.first.toJson(),
        'terminal_operation_ref':
            matches.length == 1 && matches.first.isTerminal
                ? matches.first.operationRef
                : null,
      };
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
  throw StateError('operation listing wait loop escaped');
}
Future<Map<String, Object?>> _authControls(String baseUrl, String token) async {
  final unauthHttp = http.Client();
  final wrongHttp = http.Client();
  try {
    final missing =
        await GatewayClient(baseUrl: baseUrl, httpClient: unauthHttp).isAlive();
    final wrong = await GatewayClient(
      baseUrl: baseUrl,
      httpClient: AuthedClient(wrongHttp, readToken: () => 'wrong-token'),
    ).isAlive();
    return {
      'missing_token_ok': missing,
      'wrong_token_ok': wrong,
      'token_sha256': _sha(token),
      'token_length': token.length,
    };
  } finally {
    unauthHttp.close();
    wrongHttp.close();
  }
}
Map<String, Object?> _receipt(
  String phase,
  ConnectionConfig config,
  String token,
  Map<String, Object?> phaseData,
) =>
    {
      'schema': 'flywheel.android-real-gateway-handoff-phase/v1',
      'run_id': _runIdValue(),
      'phase': phase,
      'platform': Platform.operatingSystem,
      'transport': {'mode': 'usb_reverse'},
      'connection': {
        'base_url': config.effectiveBaseUrl,
        'is_remote': config.isRemote,
        'token_sha256': _sha(token),
        'token_length': token.length,
      },
      ...phaseData,
      'limits': const [
        'USB reverse only; does not prove LAN or Tailscale reachability',
        'endpoint stub only; does not prove a live provider or release network',
        'Relay and Plexus evidence are out of this first slice',
      ],
    };
void _emit(Map<String, Object?> receipt, String token) {
  final encoded = jsonEncode(receipt);
  if (encoded.contains(token)) throw StateError('receipt leaked token');
  // ignore: avoid_print
  print('$_prefix$encoded');
}
String _runIdValue() => _runId.isNotEmpty
    ? _runId
    : 'android_real_${DateTime.now().microsecondsSinceEpoch}';
String _sha(String value) => sha256.convert(utf8.encode(value)).toString();
