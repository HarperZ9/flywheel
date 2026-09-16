import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/live_screen_models.dart';

void main() {
  final payload = base64Decode(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aSxkAAAAASUVORK5CYII=');
  LiveScreenFrame frame({String session = 'session-1', String? digest}) =>
      LiveScreenFrame.fromJson({
        'session_id': session,
        'source_id': 'display:primary',
        'source_sequence': 2,
        'aggregate_sequence': 3,
        'frame_sha256': digest ?? sha256.convert(payload).toString(),
        'captured_at_utc': '2026-09-15T10:00:00Z',
        'width': 1,
        'height': 1,
      });

  test('preview uses a fixed same-gateway route and checks actual bytes',
      () async {
    final calls = <http.Request>[];
    final client = GatewayClient(httpClient: MockClient((request) async {
      calls.add(request);
      expect(request.followRedirects, false);
      return http.Response.bytes(payload, 200,
          headers: {'content-type': 'image/png'});
    }));
    expect(await client.liveScreenPreview(frame()), payload);
    expect(calls.single.url.origin, GatewayClient.loopback);
    expect(calls.single.url.pathSegments, [
      'api',
      'live-screen',
      'sessions',
      'session-1',
      'sources',
      'display:primary',
      'frames',
      '2',
      'preview',
    ]);
    expect(calls.single.method, 'GET');
  });

  test('terminal session state ends polling without a later disconnect',
      () async {
    var calls = 0;
    final client = GatewayClient(httpClient: MockClient((_) async {
      calls++;
      if (calls > 1) return http.Response('{}', 503);
      return http.Response(
          jsonEncode({
            'events': [
              {
                'event': 'screen.session',
                'state': 'stopped',
                'session_id': 'session-1'
              }
            ]
          }),
          200);
    }));
    final events = await client.liveScreenEvents('session-1').toList();
    expect(calls, 1);
    expect(events.single['state'], 'stopped');
  });

  test('changed preview bytes cannot be labelled as an earlier frame',
      () async {
    final client = GatewayClient(
        httpClient: MockClient((_) async => http.Response.bytes(payload, 200,
            headers: {'content-type': 'image/png'})));
    await expectLater(client.liveScreenPreview(frame(digest: 'a' * 64)),
        throwsFormatException);
  });

  test('invalid identity never becomes a network request', () async {
    var calls = 0;
    final client = GatewayClient(httpClient: MockClient((_) async {
      calls++;
      return http.Response('', 500);
    }));
    await expectLater(client.liveScreenPreview(frame(session: '../other')),
        throwsFormatException);
    expect(calls, 0);
  });

  test('oversized image is rejected before returning preview bytes', () async {
    final client = GatewayClient(
        httpClient: MockClient((_) async => http.Response.bytes(
            List.filled(4 * 1024 * 1024 + 1, 0), 200,
            headers: {'content-type': 'image/png'})));
    await expectLater(client.liveScreenPreview(frame()), throwsFormatException);
  });

  test('event observation reads queue and stops at terminal event', () async {
    final calls = <http.Request>[];
    final client = GatewayClient(httpClient: MockClient((request) async {
      calls.add(request);
      return http.Response(
          jsonEncode({
            'events': [
              {'event': 'screen.stop', 'session_id': 'session-1'},
            ]
          }),
          200);
    }));
    final events = await client.liveScreenEvents('session-1').toList();
    expect(events.single['event'], 'screen.stop');
    expect(calls.length, 1);
    expect(calls.single.url.path, '/api/live-screen/sessions/session-1/poll');
    expect(calls.single.body, '{}');
    expect(calls.single.followRedirects, false);
  });

  test('event queue cannot introduce another session', () async {
    final client = GatewayClient(
        httpClient: MockClient((_) async => http.Response(
            jsonEncode({
              'events': [
                {'event': 'screen.frame', 'session_id': 'unrelated'},
              ]
            }),
            200)));
    await expectLater(
        client.liveScreenEvents('session-1').toList(), throwsFormatException);
  });

  test('duplicate source IDs fail instead of selecting ambiguous monitors',
      () async {
    final row = {
      'source_id': 'one',
      'kind': 'display',
      'label': 'Monitor',
      'backend': 'gdi',
      'available': true
    };
    final client = GatewayClient(
        httpClient: MockClient((_) async => http.Response(
            jsonEncode({
              'sources': [row, row]
            }),
            200)));
    await expectLater(client.liveScreenSources(), throwsFormatException);
  });

  test('redirect and non-image responses never become screen previews',
      () async {
    for (final status in [200, 302]) {
      final client = GatewayClient(
          httpClient: MockClient(
              (_) async => http.Response('not an image', status, headers: {
                    'content-type': 'text/html',
                    'location': 'https://example.com',
                  })));
      await expectLater(
          client.liveScreenPreview(frame()), throwsFormatException);
    }
  });
}
