import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'host_noise.dart';

const _w = 40, _h = 40;

/// A light ground with one dark antialiased vertical edge at x = 20.
Uint8List _frame() {
  final bytes = Uint8List(_w * _h * 4);
  for (var y = 0; y < _h; y++) {
    for (var x = 0; x < _w; x++) {
      final v = x < 20 ? 240 : (x == 20 ? 128 : 16);
      bytes.setAll((y * _w + x) * 4, [v, v, v, 255]);
    }
  }
  return bytes;
}

void _set(Uint8List bytes, int x, int y, int v) =>
    bytes.setAll((y * _w + x) * 4, [v, v, v, 255]);

HostNoiseVerdict _check(Uint8List test) =>
    hostNoiseVerdict(_frame(), test, _w, _h);

void main() {
  test('identical frames are accepted with no differing pixels', () {
    final verdict = _check(_frame());
    expect(verdict.accepted, isTrue);
    expect(verdict.differingPixels, 0);
  });

  test('edge coverage noise inside the neighborhood is accepted', () {
    final test = _frame();
    _set(test, 20, 3, 128 + 33); // the measured CI maximum delta
    _set(test, 20, 9, 128 - 20);
    final verdict = _check(test);
    expect(verdict.accepted, isTrue, reason: verdict.describe());
    expect(verdict.maxChannelDelta, 33);
    expect(verdict.maxOutsideNeighborhood, 0);
  });

  test('a delta above the limit is rejected even at an edge', () {
    final test = _frame();
    _set(test, 20, 3, 128 + 49);
    expect(_check(test).accepted, isFalse);
  });

  test('a new color inside a flat region is rejected', () {
    final test = _frame();
    _set(test, 5, 5, 240 - 9); // flat ground: neighborhood range is 240..240
    final verdict = _check(test);
    expect(verdict.accepted, isFalse);
    expect(verdict.maxOutsideNeighborhood, 9);
  });

  test('a faint tint over a region is rejected by the differing fraction', () {
    final test = _frame();
    for (var y = 0; y < 10; y++) {
      for (var x = 0; x < 10; x++) {
        _set(test, x, y, 240 - 4);
      }
    }
    final verdict = _check(test);
    expect(verdict.maxChannelDelta, 4);
    expect(verdict.accepted, isFalse, reason: verdict.describe());
  });

  test('a one pixel shift of the edge is rejected', () {
    final shifted = Uint8List(_w * _h * 4);
    final frame = _frame();
    for (var y = 0; y < _h; y++) {
      for (var x = 0; x < _w; x++) {
        final from = (y * _w + (x == 0 ? 0 : x - 1)) * 4;
        shifted.setAll((y * _w + x) * 4, frame.sublist(from, from + 4));
      }
    }
    expect(_check(shifted).accepted, isFalse);
  });

  test('buffers of the wrong size are rejected', () {
    expect(hostNoiseVerdict(_frame(), Uint8List(4), _w, _h).accepted, isFalse);
  });
}
