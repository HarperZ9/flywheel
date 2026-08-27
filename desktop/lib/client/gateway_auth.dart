// gateway_auth.dart — the desktop client presents the gateway's bearer token.
//
// The gateway is not public and localhost is not a wall (harness/gateway_auth.py):
// every request needs `Authorization: Bearer <token>`, where the token is minted
// by the engine into `<FLYWHEEL_HOME>/gateway.token` on first run. Without the
// header every route answers 401, `isAlive` reads that as unreachable, and the
// app reports the engine offline while a healthy engine is running. That was a
// real defect: the client sent no Authorization header on any of its 71 calls.
//
// The header is added at the HTTP layer rather than at the call sites, so a
// route added later cannot forget it.
//
// The token is read lazily and cached, never logged, and never written anywhere.
// Two lifecycle facts drive the caching rule:
//
//   * The app can start BEFORE the engine exists, so the file is often absent
//     at construction. A null cache is retried on every send, which is how the
//     app goes online moments after the engine first mints the file.
//   * A rotated token (a fresh install, a cleared home) would otherwise pin the
//     app to a stale secret. A 401 invalidates the cache, so the next request
//     re-reads from disk.

import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

const String tokenFilename = 'gateway.token';

/// Cached writable home for platforms where the environment names none. Null on
/// desktop, where HOME/USERPROFILE already resolve. Set once by
/// [initFlywheelHome] at startup, so [flywheelHome] stays synchronous for its
/// many callers.
String? _mobileHome;

/// Resolve a writable home on Android and iOS, where HOME is `/` (unwritable)
/// and USERPROFILE is unset, so every store that hangs off [flywheelHome]
/// (the paired connection, chat history, sessions, settings) persists. Uses the
/// app-private support directory, namespaced with `.flywheel` to mirror the
/// desktop layout. A no-op on desktop. It never throws: if the platform channel
/// fails the override stays null and the app runs with persistence degraded
/// rather than crashing at launch. Call it once, awaited, before the first
/// store loads.
Future<void> initFlywheelHome() async {
  if (!(Platform.isAndroid || Platform.isIOS)) return;
  try {
    final dir = await getApplicationSupportDirectory();
    _mobileHome = '${dir.path}${Platform.pathSeparator}.flywheel';
  } catch (_) {
    // Leave _mobileHome null; flywheelHome() falls back to its default.
  }
}

/// The engine's home directory, resolved exactly as the rest of the app and the
/// engine resolve it: `FLYWHEEL_HOME`, else the mobile app-private home when one
/// was resolved, else the user profile plus `.flywheel`.
String flywheelHome() {
  final env = Platform.environment;
  final explicit = env['FLYWHEEL_HOME'];
  if (explicit != null && explicit.isNotEmpty) return explicit;
  if (_mobileHome != null) return _mobileHome!;
  final profile = env['USERPROFILE'] ?? env['HOME'] ?? '.';
  return '$profile${Platform.pathSeparator}.flywheel';
}

/// The full path of the token file the engine mints.
String gatewayTokenPath() =>
    '${flywheelHome()}${Platform.pathSeparator}$tokenFilename';

/// The gateway token, or null when the engine has not minted one yet (or the
/// file cannot be read). Absence is a normal state, never an error: the app
/// simply has no engine to talk to yet.
String? readGatewayToken() {
  try {
    final f = File(gatewayTokenPath());
    if (!f.existsSync()) return null;
    final t = f.readAsStringSync().trim();
    return t.isEmpty ? null : t;
  } on FileSystemException {
    return null;
  }
}

/// An http client that presents the gateway token on every request.
///
/// Wrapping [http.BaseClient] means each request passes through [send] exactly
/// once, so every present and future call site is covered by construction. A
/// caller-supplied header is never overwritten: a test or a future caller that
/// sets its own Authorization stays in control.
class AuthedClient extends http.BaseClient {
  AuthedClient(this._inner, {String? Function()? readToken})
      : _readToken = readToken ?? readGatewayToken;

  final http.Client _inner;
  final String? Function() _readToken;
  String? _cached;

  /// Drop the cached token so the next request re-reads it from disk. Called
  /// on a 401, which is the observable signature of a rotated token.
  void invalidate() => _cached = null;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    if (!request.headers.containsKey('Authorization')) {
      // A null cache is retried every send: the engine may mint the token at
      // any moment after the app starts.
      final token = _cached ??= _readToken();
      if (token != null) request.headers['Authorization'] = 'Bearer $token';
    }
    final response = await _inner.send(request);
    if (response.statusCode == 401) invalidate();
    return response;
  }

  @override
  void close() {
    _inner.close();
    super.close();
  }
}
