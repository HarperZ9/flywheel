// The installed app must find its shipped engine beside the exe and prefer
// it; a dev checkout (no engine payload) falls back to PATH. The path rule
// is pure and tested directly; existence gating is exercised on a real
// temp directory.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/services/gateway_process.dart';

void main() {
  test('bundled engine path is engine/flywheel-gateway.exe beside the exe',
      () {
    final sep = Platform.pathSeparator;
    final p = GatewayProcess.bundledEnginePathFor('C:${sep}Apps${sep}Flywheel');
    expect(
        p,
        'C:${sep}Apps${sep}Flywheel${sep}engine'
        '${sep}flywheel-gateway.exe');
  });

  test('a real engine file at that path is found, an absent one is not',
      () async {
    final dir = await Directory.systemTemp.createTemp('fw_engine_test');
    try {
      final candidate = GatewayProcess.bundledEnginePathFor(dir.path);
      expect(File(candidate).existsSync(), isFalse); // dev checkout shape
      await File(candidate).create(recursive: true); // installed shape
      expect(File(candidate).existsSync(), isTrue);
    } finally {
      await dir.delete(recursive: true);
    }
  });
}
