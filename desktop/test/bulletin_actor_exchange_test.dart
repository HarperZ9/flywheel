import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'support/bulletin_actor_exchange.dart';

void main() {
  late Directory root;
  setUp(() {
    root = Directory.systemTemp.createTempSync('bulletin-exchange-');
  });
  tearDown(() {
    root.deleteSync(recursive: true);
  });
  test('created-only exact bytes, bounded reads and fixed names', () async {
    final exchange = ActorExchange(root.path);
    exchange.write('result.json', {'schema_version': 1}, 100);
    final record =
        await exchange.wait('result.json', 100, const Duration(seconds: 1));
    expect(record.sha256, actorDigest(utf8.encode('{"schema_version":1}')));
    expect(() => exchange.write('result.json', {}, 100),
        throwsA(isA<ActorExchangeError>()));
    expect(() => exchange.write('../outside.json', {}, 100),
        throwsA(isA<ActorExchangeError>()));
    await expectLater(
        exchange.wait('result.json', 1, const Duration(seconds: 1)),
        throwsA(isA<ActorExchangeError>()));
  });
  test(
      'duplicate keys, mismatched digest, bool version and extra fields denied',
      () async {
    final exchange = ActorExchange(root.path);
    File('${root.path}/decision.json').writeAsStringSync('{"x":1,"x":2}');
    await expectLater(
        exchange.wait('decision.json', 100, const Duration(seconds: 1)),
        throwsA(isA<ActorExchangeError>()));
    exchange.write('proposal.json', {'schema_version': 1}, 100);
    await expectLater(
        exchange.wait('proposal.json', 100, const Duration(seconds: 1),
            expectedSha: 'a' * 64),
        throwsA(isA<ActorExchangeError>()));
    for (final value in [
      {'schema_version': true},
      {'schema_version': 1, 'extra': 2}
    ]) {
      expect(() => actorFields(value, {'schema_version'}),
          throwsA(isA<ActorExchangeError>()));
    }
  });
  test('missing record times out and substituted root refuses I/O', () async {
    final exchange = ActorExchange(root.path);
    await expectLater(
        exchange.wait('decision.json', 100, const Duration(milliseconds: 10)),
        throwsA(isA<ActorExchangeError>()));
    final old = root.renameSync('${root.path}-old');
    try {
      root.createSync();
      expect(() => exchange.write('result.json', {}, 100),
          throwsA(isA<ActorExchangeError>()));
    } finally {
      old.deleteSync(recursive: true);
    }
  });
}
