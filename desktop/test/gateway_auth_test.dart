// Falsifiers for the gateway bearer-token client.
//
// The defect these pin down: the desktop client sent no Authorization header,
// so a healthy engine answered 401 and the app reported it offline forever.

import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:flywheel_desktop/client/gateway_auth.dart';

/// Records the headers of every request and replies with a scripted status.
class _Spy extends http.BaseClient {
  _Spy({this.statuses = const [200]});

  final List<int> statuses;
  final List<Map<String, String>> seen = [];
  int _i = 0;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    seen.add(Map<String, String>.from(request.headers));
    final status = statuses[_i < statuses.length ? _i : statuses.length - 1];
    _i++;
    return http.StreamedResponse(
      Stream.value(utf8.encode('{}')),
      status,
    );
  }
}

void main() {
  final uri = Uri.parse('http://127.0.0.1:8799/api/world');

  test('presents the token as a bearer header', () async {
    final spy = _Spy();
    final client = AuthedClient(spy, readToken: () => 'tok-abc');

    await client.get(uri);

    expect(spy.seen.single['Authorization'], 'Bearer tok-abc');
  });

  test('sends no Authorization header when no token exists yet', () async {
    // The app routinely starts before the engine mints a token. That must not
    // crash and must not send a bogus header.
    final spy = _Spy();
    final client = AuthedClient(spy, readToken: () => null);

    await client.get(uri);

    expect(spy.seen.single.containsKey('Authorization'), isFalse);
  });

  test('retries the read until the engine mints the token', () async {
    // The decisive lifecycle case: app up, engine down, then engine starts.
    // A token cached as null at construction would pin the app offline.
    final spy = _Spy();
    var minted = false;
    final client = AuthedClient(spy, readToken: () => minted ? 'tok-late' : null);

    await client.get(uri); // engine not up yet
    minted = true;
    await client.get(uri); // engine has since minted the token

    expect(spy.seen[0].containsKey('Authorization'), isFalse);
    expect(spy.seen[1]['Authorization'], 'Bearer tok-late');
  });

  test('reads the token once while it keeps working', () async {
    final spy = _Spy();
    var reads = 0;
    final client = AuthedClient(spy, readToken: () {
      reads++;
      return 'tok-cached';
    });

    await client.get(uri);
    await client.get(uri);
    await client.get(uri);

    expect(reads, 1, reason: 'a working token is cached, not re-read per call');
  });

  test('a 401 invalidates the cache so a rotated token is picked up', () async {
    // A fresh install or a cleared home rotates the token. Without this the app
    // stays pinned to a stale secret and never recovers.
    final spy = _Spy(statuses: [401, 200]);
    final tokens = ['tok-old', 'tok-new'];
    var i = 0;
    final client = AuthedClient(spy, readToken: () => tokens[i++]);

    await client.get(uri); // 401 with the stale token
    await client.get(uri); // must re-read

    expect(spy.seen[0]['Authorization'], 'Bearer tok-old');
    expect(spy.seen[1]['Authorization'], 'Bearer tok-new');
  });

  test('never overwrites an Authorization header a caller set', () async {
    final spy = _Spy();
    final client = AuthedClient(spy, readToken: () => 'tok-abc');

    await client.get(uri, headers: {'Authorization': 'Bearer caller-owned'});

    expect(spy.seen.single['Authorization'], 'Bearer caller-owned');
  });

  test('FLYWHEEL_HOME wins the token path when it is set', () {
    // Mirrors the engine's own resolution order (harness/gateway.py).
    final path = gatewayTokenPath();
    expect(path.endsWith(tokenFilename), isTrue);
    expect(path.contains(flywheelHome()), isTrue);
  });
}
