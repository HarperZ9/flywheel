import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:path_provider/path_provider.dart';

import '../client/bulletin_media_api.dart';
import '../models/bulletin_media_models.dart';

const bulletinPreviewBytesPath =
    '/api/gateway-grants/bulletin-media-preview-bytes';

typedef BulletinMediaBytesFetch = Future<GatewayByteResponse> Function(
    String path, Map<String, dynamic> body);

final class BulletinMediaCacheException implements Exception {
  final String code;
  const BulletinMediaCacheException(this.code);
  @override
  String toString() => code;
}

final class CachedBulletinMedia {
  final File file;
  final BulletinMediaAttachment attachment;
  const CachedBulletinMedia(this.file, this.attachment);

  void deleteBestEffort() {
    try {
      if (file.existsSync()) file.deleteSync();
    } on FileSystemException {
      // Best-effort cleanup only; the cache directory is app-owned.
    }
  }

  Future<void> delete() async => deleteBestEffort();
}

abstract interface class BulletinMediaLoader {
  Future<CachedBulletinMedia> load(BulletinMediaPreviewItem item);
}

final class BulletinMediaCache implements BulletinMediaLoader {
  final Directory? baseDir;
  final BulletinMediaBytesFetch fetch;
  final String proposalRef, previewSha256;

  const BulletinMediaCache({
    required this.proposalRef,
    required this.previewSha256,
    required this.fetch,
    this.baseDir,
  });

  factory BulletinMediaCache.gateway(GatewayBulletinMediaApi api,
          String proposalRef, String previewSha256) =>
      BulletinMediaCache(
        proposalRef: proposalRef,
        previewSha256: previewSha256,
        fetch: (path, body) {
          if (path != bulletinPreviewBytesPath) {
            throw const BulletinMediaCacheException('unsafe_route');
          }
          return api.previewBytes(
            body['proposal_ref'] as String,
            body['preview_ref'] as String,
            body['preview_sha256'] as String,
          );
        },
      );

  @override
  Future<CachedBulletinMedia> load(BulletinMediaPreviewItem item) async {
    final response = await fetch(bulletinPreviewBytesPath, {
      'schema': 'flywheel.bulletin-media-preview-bytes-request/v1',
      'proposal_ref': proposalRef,
      'preview_ref': item.preview.previewRef,
      'preview_sha256': previewSha256,
    });
    if (response.statusCode != 200) {
      throw const BulletinMediaCacheException('http_status');
    }
    final contentType = response.headers['content-type'] ?? '';
    final declaredLength = int.tryParse(response.headers['content-length'] ??
        response.bodyBytes.length.toString());
    final declaredSha = response.headers['x-flywheel-sha256'];
    final actualSha = sha256.convert(response.bodyBytes).toString();
    if (contentType != item.attachment.mediaType ||
        declaredLength != response.bodyBytes.length ||
        declaredLength != item.attachment.bytes ||
        actualSha != item.attachment.sha256 ||
        (declaredSha != null &&
            declaredSha.isNotEmpty &&
            declaredSha != actualSha)) {
      throw const BulletinMediaCacheException('byte_verification_failed');
    }
    final root = await _root();
    await root.create(recursive: true);
    await sweepStale(baseDir: root);
    final name = '${item.attachment.mediaId}.${_extension(item.attachment)}';
    final file = File('${root.path}${Platform.pathSeparator}$name');
    await file.writeAsBytes(response.bodyBytes, flush: true);
    return CachedBulletinMedia(file, item.attachment);
  }

  static Future<int> sweepStale({
    Directory? baseDir,
    Duration maxAge = const Duration(hours: 12),
    DateTime? now,
  }) async {
    final root = baseDir ?? await _defaultRoot();
    if (!await root.exists()) return 0;
    final cutoff = (now ?? DateTime.now().toUtc()).subtract(maxAge);
    var deleted = 0;
    await for (final entity in root.list(followLinks: false)) {
      if (entity is Link || await FileSystemEntity.isLink(entity.path)) {
        continue;
      }
      if (entity is! File) continue;
      try {
        final modified = (await entity.stat()).modified.toUtc();
        if (modified.isBefore(cutoff)) {
          await entity.delete();
          deleted++;
        }
      } on FileSystemException {
        // Best-effort cleanup only; the cache directory is app-owned.
      }
    }
    return deleted;
  }

  Future<Directory> _root() async {
    if (baseDir != null) return baseDir!;
    return _defaultRoot();
  }

  String _extension(BulletinMediaAttachment attachment) {
    final type = attachment.mediaType;
    if (type == 'image/png') return 'png';
    if (type == 'image/jpeg') return 'jpg';
    if (type == 'audio/mpeg') return 'mp3';
    if (type == 'audio/wav') return 'wav';
    if (type == 'video/mp4') return 'mp4';
    return switch (attachment.kind) {
      BulletinMediaKind.image => 'img',
      BulletinMediaKind.audio => 'aud',
      BulletinMediaKind.video => 'vid',
      BulletinMediaKind.invalidResponse => 'bin',
    };
  }
}

Future<Directory> _defaultRoot() async {
  final support = await getApplicationSupportDirectory();
  return Directory(
      '${support.path}${Platform.pathSeparator}bulletin-media-review-cache');
}

String cacheDebugDigest(List<int> bytes) => sha256.convert(bytes).toString();
List<int> bytesFromB64(String value) => base64Decode(value);

final class UnavailableBulletinMediaLoader implements BulletinMediaLoader {
  const UnavailableBulletinMediaLoader();
  @override
  Future<CachedBulletinMedia> load(BulletinMediaPreviewItem item) async =>
      throw const BulletinMediaCacheException('preview_unavailable');
}
