// The drift gate for lib/version.dart: the constant the UI shows must be
// the version pubspec ships. The moment a release bump touches one and not
// the other, this fails, so the About surface can never lie.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/version.dart';

void main() {
  test('appVersion matches pubspec.yaml', () {
    final line = File('pubspec.yaml')
        .readAsLinesSync()
        .firstWhere((l) => l.startsWith('version:'));
    final pubspec = line.split(':')[1].trim().split('+')[0];
    expect(appVersion, pubspec,
        reason: 'bump lib/version.dart together with pubspec.yaml');
  });
}
