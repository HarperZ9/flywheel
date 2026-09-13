part of 'json_pointer_locator.dart';

List<int> _buildLineStarts(String text) {
  final starts = <int>[0];
  for (var index = 0; index < text.length; index++) {
    if (text.codeUnitAt(index) == 0x0a) starts.add(index + 1);
  }
  return starts;
}

List<int> _buildByteOffsets(String text) {
  final offsets = List<int>.filled(text.length + 1, 0);
  var byteOffset = 0;
  var index = 0;
  while (index < text.length) {
    offsets[index] = byteOffset;
    final unit = text.codeUnitAt(index);
    if (unit <= 0x7f) {
      byteOffset += 1;
      index += 1;
    } else if (unit <= 0x7ff) {
      byteOffset += 2;
      index += 1;
    } else if (_isHighSurrogate(unit) &&
        index + 1 < text.length &&
        _isLowSurrogate(text.codeUnitAt(index + 1))) {
      offsets[index + 1] = byteOffset;
      byteOffset += 4;
      index += 2;
    } else {
      byteOffset += 3;
      index += 1;
    }
  }
  offsets[text.length] = byteOffset;
  return offsets;
}

bool _isHighSurrogate(int unit) => unit >= 0xd800 && unit <= 0xdbff;
bool _isLowSurrogate(int unit) => unit >= 0xdc00 && unit <= 0xdfff;
