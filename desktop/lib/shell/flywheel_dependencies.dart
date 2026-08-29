import 'package:http/http.dart' as http;

import '../client/gateway_auth.dart';
import '../client/gateway_client.dart';
import '../client/journey_api.dart';
import '../controllers/journey_controller.dart';
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
    required this.code,
    this.closePrompt,
    this.status,
  });

  factory FlywheelDependencies.production() {
    final conn = ConnectionStore().load();
    final client = GatewayClient(
      baseUrl: conn.effectiveBaseUrl,
      httpClient: AuthedClient(http.Client(), readToken: conn.tokenSource),
    );
    return FlywheelDependencies(
      client: client,
      gateway: GatewayProcess(),
      code: CodeBufferSession(draftStore: CodeDraftStore()),
      journey: JourneyController(
        api: GatewayJourneyApi(client),
        draftStore: JourneyDraftStore(),
        sessionStore: JourneySessionStore(),
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
  final JourneyController journey;
  final CodeBufferSession code;
  final CloseChoicePrompt? closePrompt;

  /// The typed connection probe. Null in hand-built test dependencies,
  /// where the shell falls back to the client's own liveness check; the
  /// typed route is covered by connection_state_test and the engine's
  /// desktop-status route tests.
  final GatewayStatusService? status;

  void dispose() {
    journey.dispose();
    code.dispose();
    client.close();
    gateway.stopIfOwned();
  }
}
