import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/bulletin_media_models.dart';
import 'package:flywheel_desktop/services/bulletin_media_cache.dart';

final class TestMediaLoader implements BulletinMediaLoader {
  final File file;
  int calls = 0;
  TestMediaLoader(this.file);

  @override
  Future<CachedBulletinMedia> load(BulletinMediaPreviewItem item) async {
    calls++;
    return CachedBulletinMedia(file, item.attachment);
  }
}

Finder keyed(String value) => find.byKey(ValueKey(value));
