// gateway_status.dart -- probes the engine's typed status route and maps
// every transport outcome onto a ConnectionPhase. A 401 is an auth
// problem, a refused socket is offline, an incompatible api level is a
// version mismatch; none of them may collapse into one boolean.
import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../client/gateway_auth.dart';
import '../models/connection_state.dart';

/// The outcome of one status request, before any phase mapping.
sealed class GatewayStatusOutcome {
  final int statusCode;
  const GatewayStatusOutcome(this.statusCode);
}

class GatewayStatusDoc extends GatewayStatusOutcome {
  final Map<String, dynamic> doc;
  const GatewayStatusDoc(this.doc) : super(200);
}

class GatewayStatusFailure extends GatewayStatusOutcome {
  const GatewayStatusFailure(super.statusCode);
}

class GatewayStatusService {
  /// Injectable so tests exercise every transport outcome without a
  /// network. Production supplies a real GET against /api/desktop/status.
  final Future<GatewayStatusOutcome> Function(Uri url) statusEndpoint;
  final Uri Function() endpoint;

  /// Liveness fallback for an engine that predates the status route: a
  /// 404 means an older, still-serving engine, not an offline one.
  final Future<bool> Function()? fallbackAlive;

  GatewayStatusService({
    required this.statusEndpoint,
    Uri Function()? endpoint,
    this.fallbackAlive,
  })  : endpoint = endpoint ??
            (() => Uri.parse('http://127.0.0.1:8799/api/desktop/status'));

  /// Production probe: its own authed client reading the same gateway
  /// token as the main client, so auth parity holds across pollers.
  factory GatewayStatusService.production(
      {String? baseUrl, Future<bool> Function()? fallbackAlive}) {
    final authed = AuthedClient(http.Client());
    final base = baseUrl ?? 'http://127.0.0.1:8799';
    return GatewayStatusService(
      endpoint: () => Uri.parse('$base/api/desktop/status'),
      statusEndpoint: (url) async {
        http.Response r;
        try {
          r = await authed.get(url).timeout(const Duration(seconds: 3));
        } catch (_) {
          return const GatewayStatusFailure(0);
        }
        if (r.statusCode != 200) return GatewayStatusFailure(r.statusCode);
        try {
          final v = jsonDecode(r.body);
          if (v is Map<String, dynamic>) return GatewayStatusDoc(v);
        } catch (_) {}
        return GatewayStatusFailure(r.statusCode);
      },
    );
  }

  Future<ConnectionStatus> probe() async {
    final GatewayStatusOutcome outcome;
    final pending = Completer<GatewayStatusOutcome>();
    final timer = Timer(const Duration(seconds: 4), () {
      if (!pending.isCompleted) {
        pending.complete(const GatewayStatusFailure(0));
      }
    });
    try {
      // A completer pins the awaited type to GatewayStatusOutcome: an
      // injected closure may return a covariant Future<GatewayStatusDoc>,
      // and Future.sync would hand that specialized future straight back,
      // breaking .timeout-style typing at runtime.
      unawaited(statusEndpoint(endpoint()).then(
        (value) {
          if (!pending.isCompleted) pending.complete(value);
        },
        onError: (Object e) {
          if (!pending.isCompleted) pending.completeError(e);
        },
      ));
      outcome = await pending.future;
    } catch (_) {
      return ConnectionStatus.offline;
    } finally {
      timer.cancel();
    }
    if (outcome is GatewayStatusDoc) {
      return ConnectionStatus.fromStatusDoc(outcome.doc);
    }
    if (outcome.statusCode == 404 && fallbackAlive != null) {
      try {
        if (await fallbackAlive!()) {
          return const ConnectionStatus.typed(ConnectionPhase.online,
              detail: 'engine online (status route unavailable)');
        }
      } catch (_) {}
      return ConnectionStatus.offline;
    }
    return switch (outcome.statusCode) {
      401 => const ConnectionStatus.typed(ConnectionPhase.authRequired,
          detail: 'authentication required; sign in to the engine'),
      0 => ConnectionStatus.offline,
      _ => ConnectionStatus.typed(ConnectionPhase.offline,
          detail: 'the engine answered with status ${outcome.statusCode}'),
    };
  }
}
