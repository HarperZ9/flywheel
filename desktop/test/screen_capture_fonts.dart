import 'dart:io';
import 'package:flutter/services.dart';

Future<void> loadScreenCaptureFonts() async {
  await (FontLoader('Hanken Grotesk')
        ..addFont(rootBundle.load('assets/fonts/hanken-grotesk-regular.ttf'))
        ..addFont(rootBundle.load('assets/fonts/hanken-grotesk-semibold.ttf')))
      .load();
  await (FontLoader('Cascadia Mono')
        ..addFont(rootBundle.load('assets/fonts/CascadiaMono.ttf')))
      .load();
  ByteData icons;
  try {
    icons = await rootBundle.load('fonts/MaterialIcons-Regular.otf');
  } catch (_) {
    const suffix =
        'bin/cache/artifacts/material_fonts/materialicons-regular.otf';
    final paths = <String>[];
    final root = Platform.environment['FLUTTER_ROOT'];
    if (root != null) paths.add('$root/$suffix');
    for (var dir = File(Platform.resolvedExecutable).parent;;) {
      paths.add('${dir.path}/$suffix');
      if (dir.parent.path == dir.path) break;
      dir = dir.parent;
    }
    final file = paths.map(File.new).firstWhere((f) => f.existsSync());
    icons = ByteData.sublistView(await file.readAsBytes());
  }
  await (FontLoader('MaterialIcons')..addFont(Future.value(icons))).load();
}
