// endpoint_row.dart — the provider endpoint row and the ONE credential
// ranking every surface (Chat default, model picker, Endpoints roster)
// sorts by. Split from gateway_models.dart to hold the size gate; that file
// re-exports this one, so imports stay stable.

/// A provider endpoint row (GET /api/endpoints).
class EndpointRow {
  final String name;
  final String backend;
  final String credential; // present | absent | local-none | cli-auth
  final String providerRole;
  final bool configured;
  final String accountState;
  final bool accountAuthenticated;
  final String planType;
  final bool routeReady;
  final String routeReadyReason;
  final bool runReady;
  final String runReadyReason;
  final bool readinessCheckAvailable;
  final bool readinessChecked;
  final String readinessProbe;
  final bool supervisedRunReady;

  EndpointRow({
    required this.name,
    required this.backend,
    required this.credential,
    required this.providerRole,
    required this.configured,
    this.accountState = '',
    this.accountAuthenticated = false,
    this.planType = '',
    this.routeReady = false,
    this.routeReadyReason = '',
    this.runReady = false,
    this.runReadyReason = '',
    this.readinessCheckAvailable = false,
    this.readinessChecked = false,
    this.readinessProbe = '',
    this.supervisedRunReady = false,
  });

  factory EndpointRow.fromJson(Map<String, dynamic> j) => EndpointRow(
        name: j['name'] ?? j['model'] ?? '',
        backend: j['backend'] ?? '',
        credential: j['credential'] ?? 'absent',
        providerRole: j['provider_role'] ?? '',
        configured: j['configured'] ?? false,
        accountState: j['account_state'] ?? '',
        accountAuthenticated: j['account_authenticated'] == true,
        planType: j['plan_type'] ?? '',
        routeReady: j['route_ready'] == true,
        routeReadyReason: j['route_ready_reason'] ?? '',
        runReady: j['run_ready'] == true,
        runReadyReason: j['run_ready_reason'] ?? '',
        readinessCheckAvailable: j['readiness_check_available'] == true,
        readinessChecked: j['readiness_checked'] == true,
        readinessProbe: j['readiness_probe'] ?? '',
        supervisedRunReady: j['supervised_run_ready'] == true,
      );

  bool get needsAccountAuth => name == 'claude-cli' || name == 'codex-cli';
  bool get needsRouteReady => name == 'codex-cli';
  bool get cliAuthenticated =>
      credential == 'cli-auth' && (!needsAccountAuth || accountAuthenticated);
  bool get routeAuthenticated =>
      cliAuthenticated && (!needsRouteReady || routeReady);
  bool get hasCredential =>
      credential == 'present' || cliAuthenticated || cliPresent;
  // The legacy wire label means a CLI was found, not that sign-in was checked.
  bool get cliPresent => credential == 'cli-auth';

  /// A row a first send can actually answer through: a signed-in
  /// subscription CLI, a present key, or a local tier.
  bool get usable =>
      routeAuthenticated ||
      credential == 'present' ||
      credential == 'local-none';

  String get subscriptionStatusLabel {
    if (credential != 'cli-auth') return credential == 'absent' ? 'no key' : '';
    if (needsAccountAuth && !accountAuthenticated) return 'sign-in needed';
    if (needsRouteReady && !routeReady) return 'connected; run check needed';
    return 'subscription';
  }

  String get gateLabel {
    final status = subscriptionStatusLabel;
    if (status.isEmpty || status == 'subscription') return name;
    return '$name ($status)';
  }
}

/// The one credential ranking every surface sorts by: subscription tier
/// first (the paid-for CLI), then keyed/local, then unusable.
int endpointRank(EndpointRow e) => switch (e.credential) {
      'cli-auth' when e.routeAuthenticated => 0,
      'present' => 1,
      'local-none' => 1,
      'cli-auth' => 2,
      _ => 3,
    };

/// The endpoint a fresh Chat should default to: the best USABLE row by
/// [endpointRank], or null when nothing on the roster can answer. Roster
/// order breaks ties, so the engine's own ordering still matters within a
/// tier. Never returns a keyless row -- a silent empty first send is worse
/// than an honest "no model".
EndpointRow? defaultEndpoint(List<EndpointRow> rows) {
  EndpointRow? best;
  var bestRank = 99;
  for (final r in rows) {
    if (!r.usable) continue;
    final rank = endpointRank(r);
    if (rank < bestRank) {
      best = r;
      bestRank = rank;
    }
  }
  return best;
}
