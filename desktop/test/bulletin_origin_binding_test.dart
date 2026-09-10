import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/gateway_grant_models.dart';

GatewayOperation _op(String action, Map<String, Object?> operation) =>
    GatewayOperation.exact(
      action: action,
      clientRequestId: 'request-1',
      operation: operation,
    );

void main() {
  test('a Bulletin board write names the selected origin before dispatch', () {
    final op = _op('lane.call', {
      'name': 'bulletin',
      'tool': 'board_write_post',
      'args': {'room': 'findings', 'body': 'Synthetic origin control'},
      'governance_tier': 'T2',
      'timeout': 20,
      'bulletin_base_url': 'https://bulletin.zaindharper.workers.dev',
    });
    expect(op.destination.kind, 'lane');
    expect(op.destination.ref, 'bulletin');
    expect(
      op.destination.bulletinBaseUrl,
      'https://bulletin.zaindharper.workers.dev',
    );
    expect(
      op.operation['bulletin_base_url'],
      'https://bulletin.zaindharper.workers.dev',
    );
    expect(
      op.finalBody(
        const GatewayJourneyBinding(
          'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
          'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        ),
        'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      )['bulletin_base_url'],
      'https://bulletin.zaindharper.workers.dev',
    );
  });

  test('a Bulletin board write rejects a missing or noncanonical origin', () {
    Map<String, Object?> call(Object? origin) => {
          'name': 'bulletin',
          'tool': 'board_write_post',
          'args': {'room': 'findings', 'body': 'Synthetic origin control'},
          'governance_tier': 'T2',
          'timeout': 20,
          if (origin != #missing) 'bulletin_base_url': origin,
        };
    for (final origin in [
      #missing,
      null,
      '',
      true,
      ' https://bulletin.zaindharper.workers.dev',
      'https://bulletin.zaindharper.workers.dev/',
      'https://BULLETIN.zaindharper.workers.dev',
      'https://bulletin.zaindharper.workers.dev:443',
      'http://bulletin.zaindharper.workers.dev',
      'http://127.0.0.1:80',
      'http://localhost:80',
      'http://[::1]:80',
      'https://example.invalid:443',
      'https://example.invalid.',
      'https://exa%6dple.invalid',
      'https://user:pass@bulletin.zaindharper.workers.dev',
      'https://bulletin.zaindharper.workers.dev/path',
      'https://bulletin.zaindharper.workers.dev?x=1',
      'https://bulletin.zaindharper.workers.dev#x',
      'https://[v1.example]',
      'https://[example.invalid]',
      'https://-example.invalid',
      'https://example-.invalid',
      'https://example..invalid',
      'https://${List.filled(64, 'a').join()}.invalid',
      'https://éxample.invalid',
      '${'https://'}${List.filled(294, 'a').join()}',
    ]) {
      expect(
        () => _op('lane.call', call(origin)),
        throwsA(isA<ArgumentError>()),
        reason: '$origin',
      );
    }
    for (final origin in [
      'https://127.0.0.1',
      'https://localhost',
      'https://[::1]',
      'https://[2001:db8::1]',
      'http://127.0.0.1',
      'http://localhost',
      'http://[::1]',
      'http://127.0.0.1:54321',
      'http://localhost:54321',
      'http://[::1]:54321',
    ]) {
      expect(
        _op('lane.call', call(origin)).destination.bulletinBaseUrl,
        origin,
      );
    }
  });

  test('an unrelated lane payload may carry nested Bulletin-looking data', () {
    final op = _op('lane.call', {
      'name': 'index',
      'tool': 'store.note',
      'args': {
        'payload': {
          'bulletin_base_url': 'https://bulletin.zaindharper.workers.dev',
        },
      },
    });
    expect(op.destination.kind, 'lane');
    expect(op.destination.ref, 'index');
    expect(op.destination.bulletinBaseUrl, isNull);
    expect(
      ((op.operation['args'] as Map)['payload'] as Map)['bulletin_base_url'],
      'https://bulletin.zaindharper.workers.dev',
    );
  });

  test('a Bulletin origin cannot be smuggled into another lane tool', () {
    expect(
      _op('lane.call', {
        'name': 'bulletin',
        'tool': 'board_publish_media_post',
        'args': {},
      }).destination.bulletinBaseUrl,
      isNull,
    );
    for (final operation in [
      {
        'name': 'bulletin',
        'tool': 'board_publish_media_post',
        'args': {},
        'bulletin_base_url': 'https://bulletin.zaindharper.workers.dev',
      },
      {
        'name': 'index',
        'tool': 'board_write_post',
        'args': {},
        'bulletin_base_url': 'https://bulletin.zaindharper.workers.dev',
      },
      {
        'name': 'bulletin',
        'tool': 'board_write_post',
        'args': {
          'bulletin_base_url': 'https://bulletin.zaindharper.workers.dev',
        },
        'bulletin_base_url': 'https://bulletin.zaindharper.workers.dev',
      },
    ]) {
      expect(() => _op('lane.call', operation), throwsA(isA<ArgumentError>()));
    }
  });

  test('a caller-provided destination cannot hide the Bulletin origin', () {
    final operation = {
      'name': 'bulletin',
      'tool': 'board_write_post',
      'args': {'room': 'findings', 'body': 'Synthetic origin control'},
      'governance_tier': 'T2',
      'timeout': 20,
      'bulletin_base_url': 'https://bulletin.zaindharper.workers.dev',
    };
    expect(
      () => GatewayOperation.exact(
        action: 'lane.call',
        clientRequestId: 'request-1',
        destination: const GatewayDestination('lane', 'bulletin'),
        operation: operation,
      ),
      throwsA(isA<ArgumentError>()),
    );
    expect(
      () => GatewayOperation.exact(
        action: 'lane.call',
        clientRequestId: 'request-1',
        destination: const GatewayDestination(
          'lane',
          'bulletin',
          'https://example.invalid',
        ),
        operation: operation,
      ),
      throwsA(isA<ArgumentError>()),
    );
  });
}
