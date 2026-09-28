import 'dart:convert';
import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/services/inspect_file_picker.dart';

void main() {
  test('readInspectFileBytes respects optional byte limit', () async {
    final dir = Directory.systemTemp.createTempSync('fw-inspect-picker-');
    addTearDown(() => dir.deleteSync(recursive: true));
    final file = File('${dir.path}/packet.json');
    await file.writeAsString('0123456789abcdef');

    final bounded = await readInspectFileBytes(XFile(file.path), maxBytes: 8);
    final unbounded = await readInspectFileBytes(XFile(file.path));

    expect(bounded.length, 9);
    expect(utf8.decode(unbounded), '0123456789abcdef');
  });
}
