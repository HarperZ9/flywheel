import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

String rowanActionCueBytesSha256(Uint8List bytes) =>
    sha256.convert(bytes).toString();

String rowanActionCueSha256(Object? value) =>
    sha256.convert(utf8.encode(jsonEncode(_stable(value)))).toString();

Object? _stable(Object? value) {
  if (value is Map) {
    final entries = value.entries.toList()
      ..sort(
          (left, right) => left.key.toString().compareTo(right.key.toString()));
    return {
      for (final entry in entries) entry.key.toString(): _stable(entry.value),
    };
  }
  if (value is Iterable) return value.map(_stable).toList(growable: false);
  return value;
}
