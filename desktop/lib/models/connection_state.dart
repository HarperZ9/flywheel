// connection_state.dart -- typed connection truth for the desktop shell.
//
// One boolean "alive" cannot distinguish a degraded engine from an
// authentication problem or an incompatible client, and each demands a
// different next action. This model maps the gateway's read-only
// flywheel.desktop-status/v1 facts (plus transport failures) onto the
// six canonical phases from the completion spec. Presentation renders
// the phase; it never derives it.

enum ConnectionPhase {
  starting,
  online,
  degraded,
  offline,
  authRequired,
  versionMismatch,
}

class ConnectionStatus {
  final ConnectionPhase phase;
  final int lanesLive;
  final int lanesTotal;
  final String detail;

  const ConnectionStatus.typed(this.phase,
      {this.lanesLive = 0, this.lanesTotal = 0, this.detail = ''});

  /// The shell keeps serving views in these phases; the rest are hard
  /// stops with their own honest empty states.
  bool get alive => phase == ConnectionPhase.online ||
      phase == ConnectionPhase.degraded;

  static const ConnectionStatus starting =
      ConnectionStatus.typed(ConnectionPhase.starting, detail: 'connecting…');
  static const ConnectionStatus offline = ConnectionStatus.typed(
      ConnectionPhase.offline,
      detail: 'engine offline');

  /// Parse a flywheel.desktop-status/v1 document. Missing or malformed
  /// fields degrade to a typed offline with an honest detail line; they
  /// never crash and never invent a healthy state.
  static ConnectionStatus fromStatusDoc(Map<String, dynamic> doc) {
    if (doc['schema'] != 'flywheel.desktop-status/v1') {
      return const ConnectionStatus.typed(ConnectionPhase.offline,
          detail: 'the engine did not report a known status schema');
    }
    final live = doc['lanes_live'];
    final total = doc['lanes_total'];
    final lanesLive = live is int && live >= 0 ? live : 0;
    final lanesTotal = total is int && total >= lanesLive ? total : lanesLive;
    final compatible = doc['compatible'];
    final status = doc['status'];
    if (compatible == false || status == 'incompatible') {
      return ConnectionStatus.typed(ConnectionPhase.versionMismatch,
          lanesLive: lanesLive,
          lanesTotal: lanesTotal,
          detail: 'this desktop build speaks a different API version than '
              'the engine; update one of them');
    }
    if (status == 'degraded') {
      return ConnectionStatus.typed(ConnectionPhase.degraded,
          lanesLive: lanesLive,
          lanesTotal: lanesTotal,
          detail: '$lanesLive/$lanesTotal lanes live · degraded');
    }
    if (status == 'ok') {
      return ConnectionStatus.typed(ConnectionPhase.online,
          lanesLive: lanesLive,
          lanesTotal: lanesTotal,
          detail: '$lanesLive/$lanesTotal lanes live');
    }
    return const ConnectionStatus.typed(ConnectionPhase.offline,
        detail: 'the engine reported an unknown status');
  }
}
