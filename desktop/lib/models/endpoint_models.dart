// endpoint_models.dart — typed models for the endpoint health roster and the
// adaptive-routing scoreboard. Credential fields are presence booleans only;
// the gateway never sends key values and this app never asks for them.

/// A local inference tier (GET /api/endpoints/health → local[]).
class LocalTier {
  final String name;
  final String kind; // serve | ollama
  final bool healthy;
  final String detail; // model_ref or version

  LocalTier(
      {required this.name,
      required this.kind,
      required this.healthy,
      required this.detail});

  factory LocalTier.fromJson(Map<String, dynamic> j) => LocalTier(
        name: j['name'] ?? '',
        kind: j['kind'] ?? '',
        healthy: j['healthy'] ?? false,
        detail: '${j['model_ref'] ?? j['version'] ?? ''}',
      );
}

/// A hosted provider row (GET /api/endpoints/health → enterprise[]).
class HostedTier {
  final String name;
  final String model;
  final bool credentialPresent;
  final String keyEnv; // the env var NAME only
  final String access; // subscription | api | none — the primary usable tier
  final bool subscriptionPresent; // official CLI on PATH (claude max / codex plan)
  final String subscriptionCli; // the CLI binary NAME only, never a token

  HostedTier(
      {required this.name,
      required this.model,
      required this.credentialPresent,
      required this.keyEnv,
      this.access = 'none',
      this.subscriptionPresent = false,
      this.subscriptionCli = ''});

  bool get usable => access != 'none';

  factory HostedTier.fromJson(Map<String, dynamic> j) => HostedTier(
        name: j['name'] ?? '',
        model: j['model'] ?? '',
        credentialPresent: j['credential_present'] ?? false,
        keyEnv: j['key_env'] ?? '',
        // Degrade gracefully if the gateway predates subscription-first fields.
        access: j['access'] ??
            (((j['credential_present'] ?? false) == true) ? 'api' : 'none'),
        subscriptionPresent: j['subscription_present'] ?? false,
        subscriptionCli: j['subscription_cli'] ?? '',
      );
}

/// The endpoint health roster (GET /api/endpoints/health).
class EndpointHealthDoc {
  final List<LocalTier> local;
  final List<HostedTier> hosted;
  final int localHealthy;
  final int localTotal;
  final int hostedConfigured;
  final int subscriptionAvailable; // hosted providers usable via subscription CLI
  final int enterpriseUsable; // hosted providers usable at all (subscription or key)

  EndpointHealthDoc(
      {required this.local,
      required this.hosted,
      required this.localHealthy,
      required this.localTotal,
      required this.hostedConfigured,
      this.subscriptionAvailable = 0,
      this.enterpriseUsable = 0});

  factory EndpointHealthDoc.fromJson(Map<String, dynamic> j) =>
      EndpointHealthDoc(
        local: ((j['local'] ?? []) as List)
            .map((e) => LocalTier.fromJson(e as Map<String, dynamic>))
            .toList(),
        hosted: ((j['enterprise'] ?? []) as List)
            .map((e) => HostedTier.fromJson(e as Map<String, dynamic>))
            .toList(),
        localHealthy: j['local_healthy'] ?? 0,
        localTotal: j['local_total'] ?? 0,
        hostedConfigured: j['enterprise_configured'] ?? 0,
        subscriptionAvailable: j['subscription_available'] ?? 0,
        enterpriseUsable: j['enterprise_usable'] ?? 0,
      );
}

/// One provider's observed routing record (GET /api/router/stats).
class ProviderScore {
  final String name;
  final int attempts;
  final int successes;
  final double successRate;
  final double meanLatency;
  final bool circuitOpen;
  final double score;

  ProviderScore(
      {required this.name,
      required this.attempts,
      required this.successes,
      required this.successRate,
      required this.meanLatency,
      required this.circuitOpen,
      required this.score});

  static List<ProviderScore> listFromStats(Map<String, dynamic> stats) {
    final providers = stats['providers'];
    if (providers is! Map) return [];
    final rows = <ProviderScore>[];
    providers.forEach((name, v) {
      if (v is! Map) return;
      rows.add(ProviderScore(
        name: '$name',
        attempts: (v['attempts'] ?? 0) as int,
        successes: (v['successes'] ?? 0) as int,
        successRate: ((v['success_rate'] ?? 0) as num).toDouble(),
        meanLatency: ((v['mean_latency'] ?? 0) as num).toDouble(),
        circuitOpen: v['circuit_open'] ?? false,
        score: ((v['score'] ?? 0) as num).toDouble(),
      ));
    });
    rows.sort((a, b) => b.score.compareTo(a.score));
    return rows;
  }
}
