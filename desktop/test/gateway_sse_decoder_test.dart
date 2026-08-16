import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/gateway_sse_decoder.dart';

List<List<int>> _chunks(String value, List<int> cuts, {bool bom = false}) {
  final bytes = <int>[if (bom) ...utf8.encode('\ufeff'), ...utf8.encode(value)];
  final result = <List<int>>[];
  var start = 0;
  for (final cut in cuts) {
    final end = cut.clamp(start, bytes.length);
    result.add(bytes.sublist(start, end));
    start = end;
  }
  if (start < bytes.length) result.add(bytes.sublist(start));
  return result;
}

Future<List<GatewaySseEvent>> _decode(String wire,
        {List<int> cuts = const [],
        bool bom = false,
        GatewaySseDecoder decoder = const GatewaySseDecoder()}) =>
    Stream<List<int>>.fromIterable(_chunks(wire, cuts, bom: bom))
        .transform(decoder)
        .toList();

void main() {
  test('decoder handles split UTF-8 BOM comments colon and every newline',
      () async {
    const wire = ': ignored\r'
        'id: 1\r'
        'event:snapshot\r'
        'data: {"text":"café"}\r'
        '\r'
        'id: 2\n'
        'event: progress\n'
        'data: {"type":\n'
        'data: "progress"}\n\n'
        'id: 3\r\n'
        'event: terminal\r\n'
        'data: {"state":"completed"}\r\n\r\n'
        'id: 4\r\n'
        'data: [DONE]\r\n\r\n';
    final cafe = utf8.encode('\ufeff$wire').indexOf(0xc3);
    final events = await _decode(wire,
        bom: true, cuts: [1, 2, cafe + 1, cafe + 2, cafe + 9]);

    expect(events.map((event) => event.id), [1, 2, 3, 4]);
    expect(events.map((event) => event.event),
        ['snapshot', 'progress', 'terminal', 'done']);
    expect(events[0].data, {'text': 'café'});
    expect(events[1].data, {'type': 'progress'});
    expect(events.last.isDone, isTrue);
  });

  test('EOF flushes a complete terminal but rejects incomplete observation',
      () async {
    final terminal =
        await _decode('id: 1\nevent: terminal\ndata: {"state":"failed"}');
    expect(terminal.single.event, 'terminal');

    await expectLater(
        _decode('id: 1\nevent: snapshot\ndata: {"state":"running"}\n\n'),
        throwsA(isA<GatewaySseException>()
            .having((e) => e.code, 'code', 'INVALID_RESPONSE')));
  });

  test('decoder rejects non-monotonic ids malformed JSON and false DONE',
      () async {
    for (final wire in <String>[
      'id: 2\nevent: snapshot\ndata: {}\n\n'
          'id: 2\nevent: terminal\ndata: {}\n\n',
      'id: 1\nevent: terminal\ndata: {bad}\n\n',
      'id: 1\nevent: terminal\ndata: {"state":1,"state":2}\n\n',
      'id: 1\nevent: terminal\ndata: {"a":1,"\\u0061":2}\n\n',
      'id: 1\nevent: terminal\ndata: "[DONE]"\n\n',
      'id: 1\ndata: [DONE] \n\n',
    ]) {
      await expectLater(
          _decode(wire),
          throwsA(isA<GatewaySseException>()
              .having((e) => e.code, 'code', 'INVALID_RESPONSE')));
    }
  });

  test('line event and buffered limits fail closed', () async {
    for (final value in <(GatewaySseDecoder, String)>[
      (
        const GatewaySseDecoder(lineLimit: 8),
        'id: 1\nevent: terminal\ndata: {"long":true}\n\n'
      ),
      (
        const GatewaySseDecoder(eventLimit: 16),
        'id: 1\nevent: terminal\ndata: {"long":true}\n\n'
      ),
      (const GatewaySseDecoder(bufferLimit: 8), '123456789'),
    ]) {
      await expectLater(
          _decode(value.$2, decoder: value.$1),
          throwsA(isA<GatewaySseException>()
              .having((e) => e.code, 'code', 'INVALID_RESPONSE')));
    }
  });
}
