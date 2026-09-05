// remote_surface.dart - whether a phone could reach this workstation.
//
// The relay card said "coding agent + remote access" and showed runs and
// sessions. The remote half runs as its own process, so the app had nothing
// to render for it and the kicker was a claim the view could not support.
//
// relay owns this answer and reports it; nothing here is recomputed. Values
// never arrive: credential keys come back as booleans, and the fields that do
// carry a value (the public URL, the listen address, the origins) are not
// credentials.

/// How far the remote surface is set up. Ordered by what an operator has to
/// do next, not by severity.
enum RemoteReach {
  /// relay did not answer, or this relay build predates the readout. Not the
  /// same fact as the surface being off, and never rendered as one.
  unknown,

  /// The surface stays off: no token, so the entrypoint exits at startup.
  off,

  /// Serving, but with the static bearer only. The phone connector needs all
  /// six OAuth keys and does not say so when it is short one.
  bearerOnly,

  /// Serving with the phone connector on.
  paired,
}

class RemoteSurface {
  /// False when relay could not be reached or does not report this. The
  /// reason then carries what went wrong instead of what is configured.
  final bool reported;
  final String reason;
  final bool configured;
  final bool oauthConfigured;

  /// The keys the phone connector is still waiting on, named but never valued.
  final List<String> oauthMissing;
  final bool tlsConfigured;
  final bool remoteExecAllowed;
  final String publicUrl;
  final List<String> allowedOrigins;
  final String listenHost;
  final String listenPort;

  /// The env file relay consulted, and whether it was there. "Off" and "I read
  /// the wrong file" are different facts and an operator needs them apart.
  final String envFile;
  final bool envFileFound;

  /// Which keys are set. Booleans by construction on relay's side.
  final Map<String, bool> keysPresent;

  const RemoteSurface({
    this.reported = false,
    this.reason = '',
    this.configured = false,
    this.oauthConfigured = false,
    this.oauthMissing = const [],
    this.tlsConfigured = false,
    this.remoteExecAllowed = false,
    this.publicUrl = '',
    this.allowedOrigins = const [],
    this.listenHost = '',
    this.listenPort = '',
    this.envFile = '',
    this.envFileFound = false,
    this.keysPresent = const {},
  });

  RemoteReach get reach {
    if (!reported) return RemoteReach.unknown;
    if (!configured) return RemoteReach.off;
    return oauthConfigured ? RemoteReach.paired : RemoteReach.bearerOnly;
  }

  /// The listen address, or empty when relay reported neither half. Never
  /// half-printed: a host with no port is not an address you can dial.
  String get listen =>
      listenHost.isEmpty || listenPort.isEmpty ? '' : '$listenHost:$listenPort';

  factory RemoteSurface.fromJson(Map<String, dynamic> json) {
    final listenRaw = json['listen'];
    final listen = listenRaw is Map ? listenRaw : const {};
    return RemoteSurface(
      reported: json['reported'] == true,
      reason: '${json['reason'] ?? ''}',
      configured: json['configured'] == true,
      oauthConfigured: json['oauth_configured'] == true,
      oauthMissing: _strings(json['oauth_missing']),
      tlsConfigured: json['tls_configured'] == true,
      remoteExecAllowed: json['remote_exec_allowed'] == true,
      publicUrl: _text(json['public_url']),
      allowedOrigins: _strings(json['allowed_origins']),
      listenHost: _text(listen['host']),
      listenPort: _text(listen['port']),
      envFile: _text(json['env_file']),
      envFileFound: json['env_file_found'] == true,
      keysPresent: _flags(json['keys_present']),
    );
  }

  /// Null is relay saying "not set", which is not the string "null".
  static String _text(Object? v) => v == null ? '' : '$v';

  static List<String> _strings(Object? v) =>
      v is List ? [for (final e in v) if (e != null) '$e'] : const [];

  /// A non-boolean here would be relay reporting something other than
  /// presence, which is exactly what must never render as presence.
  static Map<String, bool> _flags(Object? v) => v is Map
      ? {for (final e in v.entries) '${e.key}': e.value == true}
      : const {};
}
