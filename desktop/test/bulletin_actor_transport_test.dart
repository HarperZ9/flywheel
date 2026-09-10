import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'support/bulletin_actor_transport.dart';

class _Fake extends http.BaseClient {
  _Fake(this.response);
  final Future<http.StreamedResponse> Function(http.BaseRequest) response;
  int sends = 0;
  bool closed = false;
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    sends++;
    return response(request);
  }

  @override
  void close() {
    closed = true;
  }
}

void main() {
  final origin = Uri.parse('http://127.0.0.1:12345');
  const route = '/api/gateway-grants/capabilities';
  test('denies nonliteral origins and unexpected route before inner send',
      () async {
    final fake =
        _Fake((_) async => http.StreamedResponse(Stream.value([1]), 200));
    expect(
        () => ActorGatewayTransport(
            Uri.parse('http://localhost:12345'), 'private',
            inner: fake),
        throwsA(isA<ActorTransportError>()));
    final client = ActorGatewayTransport(origin, 'private', inner: fake);
    for (final uri in [
      origin.replace(path: '/api/route'),
      origin.replace(path: route, query: 'x=1'),
      Uri.parse('http://127.0.0.2:12345$route')
    ]) {
      await expectLater(client.post(uri), throwsA(isA<ActorTransportError>()));
    }
    expect(fake.sends, 0);
  });
  test('binds token, disables redirects and persistence, refuses route replay',
      () async {
    final events = <String>[];
    final fake = _Fake((request) async {
      expect(request.headers['authorization'], 'Bearer private');
      expect(request.followRedirects, isFalse);
      expect(request.persistentConnection, isFalse);
      return http.StreamedResponse(Stream.value([123, 125]), 200);
    });
    final client = ActorGatewayTransport(origin, 'private',
        inner: fake, onEvent: (stage, path) => events.add(stage));
    expect((await client.post(origin.replace(path: route))).body, '{}');
    await expectLater(client.post(origin.replace(path: route)),
        throwsA(isA<ActorTransportError>()));
    expect(fake.sends, 1);
    expect(events, ['request_entered', 'response_received']);
  });
  test('redirect and oversized incremental response close without retry',
      () async {
    for (final redirect in [true, false]) {
      final fake = _Fake((_) async => http.StreamedResponse(
          Stream.fromIterable([
            [1, 2],
            [3, 4]
          ]),
          redirect ? 302 : 200,
          headers: {'location': 'https://example.invalid/'}));
      final client =
          ActorGatewayTransport(origin, 'private', inner: fake, maxBytes: 3);
      await expectLater(client.post(origin.replace(path: route)),
          throwsA(isA<ActorTransportError>()));
      expect(fake.sends, 1);
      expect(fake.closed, isTrue);
    }
  });
  test('deadline aborts stalled body and recorder failure prevents I/O',
      () async {
    final stream = StreamController<List<int>>();
    final fake = _Fake((_) async => http.StreamedResponse(stream.stream, 200));
    final client = ActorGatewayTransport(origin, 'private',
        inner: fake, timeout: const Duration(milliseconds: 15));
    await expectLater(client.post(origin.replace(path: route)),
        throwsA(isA<ActorTransportError>()));
    expect(fake.closed, isTrue);
    await stream.close();
    final never = _Fake((_) async => throw StateError('must not send'));
    final failed = ActorGatewayTransport(origin, 'private',
        inner: never,
        onEvent: (_, path) => throw StateError('recorder failure'));
    await expectLater(failed.post(origin.replace(path: route)),
        throwsA(isA<ActorTransportError>()));
    expect(never.sends, 0);
    expect(failed.recordingFailed, isTrue);
  });
  test('oversize request never sends and duplicate response keys never pass',
      () async {
    final fake = _Fake((_) async =>
        http.StreamedResponse(Stream.value(utf8.encode('{"x":1,"x":2}')), 200));
    final client =
        ActorGatewayTransport(origin, 'private', inner: fake, maxBytes: 100);
    await expectLater(client.post(origin.replace(path: route), body: 'x' * 101),
        throwsA(isA<ActorTransportError>()));
    expect(fake.sends, 0);
    await expectLater(client.post(origin.replace(path: route)),
        throwsA(isA<ActorTransportError>()));
    expect(fake.sends, 1);
    expect(fake.closed, isTrue);
  });
  test('post-response recorder failure closes all later routes', () async {
    final fake = _Fake(
        (_) async => http.StreamedResponse(Stream.value([123, 125]), 200));
    final client = ActorGatewayTransport(origin, 'private', inner: fake,
        onEvent: (stage, path) {
      if (stage == 'response_received') {
        throw StateError('synthetic sink failure');
      }
    });
    await expectLater(client.post(origin.replace(path: route)),
        throwsA(isA<ActorTransportError>()));
    expect(client.recordingFailed, isTrue);
    await expectLater(
        client.post(origin.replace(path: '/api/gateway-grants/read')),
        throwsA(isA<ActorTransportError>()));
    expect(fake.sends, 1);
  });
}
