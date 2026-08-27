// connection_config.dart -- the gateway CONNECTION the app talks to.
//
// Desktop default is loopback plus the engine's local gateway.token, so a machine
// running its own engine behaves exactly as before. To reach the SAME gateway from
// another device, an operator pairs a remote base URL and a bearer token here, and
// the one app then talks to the PC's gateway with no code fork.
//
// Kept separate from DesktopSettings (UI state only): a connection carries a token,
// and the app keeps UI state and connection identity apart. The token is a paired
// bearer for the operator's OWN gateway, the same class of secret as the local
// gateway.token file, never a model-provider key (those stay in the engine
// keychain, per the canon). Persisted to <FLYWHEEL_HOME>/connection.json; an absent
// file is the loopback default.

import 'dart:convert';
import 'dart:io';

import '../client/gateway_auth.dart' show flywheelHome, readGatewayToken;

/// The default gateway origin for a locally run engine.
const String loopbackGateway = 'http://127.0.0.1:8799';

/// Where the app connects and how it authenticates. A null [baseUrl] means the
/// loopback default; a null [token] means fall back to the local gateway.token.
class ConnectionConfig {
  const ConnectionConfig({this.baseUrl, this.token});

  final String? baseUrl;
  final String? token;

  /// True when a remote gateway has been paired (a phone, or a second machine).
  bool get isRemote => baseUrl != null && baseUrl!.isNotEmpty;

  /// The base URL to build the client with, never null.
  String get effectiveBaseUrl => isRemote ? baseUrl! : loopbackGateway;

  /// A token source for AuthedClient: the paired token when set, otherwise the
  /// local gateway.token via readGatewayToken(), so desktop stays byte-identical.
  String? Function() get tokenSource => () =>
      (token != null && token!.isNotEmpty) ? token : readGatewayToken();

  Map<String, dynamic> toJson() => {
        if (isRemote) 'base_url': baseUrl,
        if (token != null && token!.isNotEmpty) 'token': token,
      };

  factory ConnectionConfig.fromJson(Map<String, dynamic> j) => ConnectionConfig(
        baseUrl: j['base_url'] is String && (j['base_url'] as String).isNotEmpty
            ? j['base_url'] as String
            : null,
        token: j['token'] is String && (j['token'] as String).isNotEmpty
            ? j['token'] as String
            : null,
      );
}

/// Persists the paired connection beside the engine's own home. Mirrors the
/// other stores: an injectable [file] for tests, a defensive load that never
/// throws, and a save that creates the parent directory.
class ConnectionStore {
  ConnectionStore({File? file}) : storageFile = file ?? _defaultFile();

  final File storageFile;

  static File _defaultFile() =>
      File('${flywheelHome()}${Platform.pathSeparator}connection.json');

  ConnectionConfig load() {
    try {
      if (!storageFile.existsSync()) return const ConnectionConfig();
      final decoded = jsonDecode(storageFile.readAsStringSync());
      if (decoded is! Map<String, dynamic>) return const ConnectionConfig();
      return ConnectionConfig.fromJson(decoded);
    } catch (_) {
      // A corrupt or unreadable file must never block launch.
      return const ConnectionConfig();
    }
  }

  void save(ConnectionConfig config) {
    storageFile.parent.createSync(recursive: true);
    storageFile.writeAsStringSync(jsonEncode(config.toJson()));
  }

  /// Return to the loopback default by removing the paired connection.
  void clear() {
    try {
      if (storageFile.existsSync()) storageFile.deleteSync();
    } catch (_) {}
  }
}
