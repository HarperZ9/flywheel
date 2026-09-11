import 'package:http/http.dart' as http;
import 'dart:io' show Platform;

import '../client/gateway_auth.dart';
import '../client/gateway_client.dart';
import '../client/journey_api.dart';
import '../controllers/journey_controller.dart';
import '../controllers/rowan_operation_controller.dart';
import '../ide/code_buffer_session.dart';
import '../ide/unsaved_work_guard.dart';
import '../services/code_draft_store.dart';
import '../services/connection_config.dart';
import '../services/gateway_process.dart';
import '../services/gateway_status.dart';
import '../services/journey_draft_store.dart';
import '../services/journey_session_store.dart';

final class FlywheelDependencies {
  const FlywheelDependencies({
    required this.client,
    required this.gateway,
    required this.journey,
    required this.rowan,
    required this.code,
    this.closePrompt,
    this.status,
    this.autoStartBundledEngine = false,
  });

  factory FlywheelDependencies.production() {
    final connectionStore = ConnectionStore();
    final conn = connectionStore.load();
    final client = GatewayClient(
      baseUrl: conn.effectiveBaseUrl,
      httpClient: AuthedClient(http.Client(), readToken: conn.tokenSource),
    );
    final journeySessionStore = JourneySessionStore();
    return FlywheelDependencies(
      client: client,
      gateway: GatewayProcess(),
      autoStartBundledEngine: !(Platform.isAndroid || Platform.isIOS) &&
          connectionStore.loadState == ConnectionLoadState.absent &&
          !conn.isRemote &&
          conn.token == null &&
          GatewayProcess.bundledEngine() != null,
      code: CodeBufferSession(draftStore: CodeDraftStore()),
      journey: JourneyController(
        api: GatewayJourneyApi(client),
        draftStore: JourneyDraftStore(),
        sessionStore: journeySessionStore,
      ),
      rowan: RowanOperationController(
        client,
        sessionStore: journeySessionStore,
      ),
      status: GatewayStatusService.production(
        baseUrl: client.baseUrl,
        readToken: conn.tokenSource,
        fallbackAlive: () => client.isAlive(),
      ),
    );
  }

  final GatewayClient client;
  final GatewayProcess gateway;
  final bool autoStartBundledEngine;
  final JourneyController journey;
  final RowanOperationController rowan;
  final CodeBufferSession code;
  final CloseChoicePrompt? closePrompt;

  /// The typed connection probe. Null in hand-built test dependencies,
  /// where the shell falls back to the client's own liveness check; the
  /// typed route is covered by connection_state_test and the engine's
  /// desktop-status route tests.
  final GatewayStatusService? status;

  void dispose() {
    journey.dispose();
    rowan.dispose();
    code.dispose();
    client.close();
    gateway.stopIfOwned();
  }
}
