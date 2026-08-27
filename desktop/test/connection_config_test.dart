// Falsifiers for the paired gateway connection: the one app can target a REMOTE
// gateway with a paired token, and defaults to loopback plus the local token so a
// desktop running its own engine is byte-identical to before.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:flywheel_desktop/client/gateway_auth.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/services/connection_config.dart';

/// Records each request and replies 200, so a client's target host and headers
/// are observable without a live gateway.
class _Spy extends http.BaseClient {
  final List<http.BaseRequest> seen = [];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    seen.add(request);
    return http.StreamedResponse(Stream.value(utf8.encode('{}')), 200);
  }
}

void main() {
  test('defaults to loopback with no paired token', () {
    const c = ConnectionConfig();
    expect(c.isRemote, isFalse);
    expect(c.effectiveBaseUrl, GatewayClient.loopback);
  });

  test('a paired remote base url is used and reads as remote', () {
    const c = ConnectionConfig(baseUrl: 'https://tunnel.example.com', token: 'paired');
    expect(c.isRemote, isTrue);
    expect(c.effectiveBaseUrl, 'https://tunnel.example.com');
    expect(c.tokenSource(), 'paired');
  });

  test('an unpaired token source falls back to the local gateway.token', () {
    const c = ConnectionConfig(baseUrl: 'https://x'); // remote host, no paired token
    expect(() => c.tokenSource(), returnsNormally); // defers to readGatewayToken()
  });

  test('the store round-trips a paired connection under a temp home', () {
    final dir = Directory.systemTemp.createTempSync('conn-');
    final file = File('${dir.path}/connection.json');
    ConnectionStore(file: file)
        .save(const ConnectionConfig(baseUrl: 'https://pc.example', token: 'tok-1'));
    final loaded = ConnectionStore(file: file).load();
    expect(loaded.baseUrl, 'https://pc.example');
    expect(loaded.token, 'tok-1');
    expect(loaded.isRemote, isTrue);
  });

  test('an absent file is the loopback default', () {
    final dir = Directory.systemTemp.createTempSync('conn-');
    final loaded = ConnectionStore(file: File('${dir.path}/none.json')).load();
    expect(loaded.isRemote, isFalse);
    expect(loaded.effectiveBaseUrl, GatewayClient.loopback);
  });

  test('a corrupt file degrades to the default, never throws', () {
    final dir = Directory.systemTemp.createTempSync('conn-');
    final file = File('${dir.path}/connection.json')..writeAsStringSync('{not json');
    expect(ConnectionStore(file: file).load().isRemote, isFalse);
  });

  test('clear removes the pairing, returning to loopback', () {
    final dir = Directory.systemTemp.createTempSync('conn-');
    final file = File('${dir.path}/connection.json');
    final store = ConnectionStore(file: file)
      ..save(const ConnectionConfig(baseUrl: 'https://x', token: 't'));
    store.clear();
    expect(file.existsSync(), isFalse);
    expect(store.load().isRemote, isFalse);
  });

  test('a client built from a remote connection targets that host with the token',
      () async {
    const conn = ConnectionConfig(baseUrl: 'https://pc.example.com', token: 'paired-tok');
    final spy = _Spy();
    final client = GatewayClient(
      baseUrl: conn.effectiveBaseUrl,
      httpClient: AuthedClient(spy, readToken: conn.tokenSource),
    );
    await client.isAlive();
    expect(spy.seen.single.url.host, 'pc.example.com');
    expect(spy.seen.single.headers['Authorization'], 'Bearer paired-tok');
  });
}
