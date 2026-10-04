import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'host_noise_comparator.dart';

/// Every golden in this directory compares exactly first and then accepts
/// only measured host rasterization noise. See host_noise.dart for the data
/// and the limits.
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  final current = goldenFileComparator;
  if (current is LocalFileComparator) {
    goldenFileComparator = HostNoiseComparator(
        current.basedir.resolve('flutter_test_config.dart'));
  }
  await testMain();
}
