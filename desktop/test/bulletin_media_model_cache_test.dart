import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/bulletin_media_api.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/bulletin_media_models.dart';
import 'package:flywheel_desktop/services/bulletin_media_cache.dart';
import 'package:http/http.dart' as http;

import 'bulletin_media_test_support.dart';
import 'bulletin_media_canonical_backend_test_support.dart';

void main() {
  test('parses review with public body, media, preview refs, and operation',
      () {
    final response = BulletinMediaPreviewResponse.fromJson(
        previewResponseJson(clientRequestId: 'bulletin_media_request_001'));

    expect(response.invalidResponse, isFalse);
    expect(response.review.post.body, 'The final public post body.');
    expect(response.review.items.single.preview.previewRef, previewRef);
    expect(response.operation?.tool, 'board_publish_media_post');
    expect(response.operation?.destination.ref, 'bulletin');
  });

  test('gateway client consumes canonical backend run and artifact envelopes',
      () async {
    Future<void> exercise(String runId, String title) async {
      final backend = await startCanonicalBackend(runId: runId, title: title);
      final client =
          GatewayClient(baseUrl: backend.baseUrl, httpClient: http.Client());
      try {
        final api = GatewayBulletinMediaApi(client);
        final runs = await api.listRuns();
        final artifacts = await api.listArtifacts(runId);

        expect(runs.single.runId, runId);
        expect(runs.single.title, title);
        expect(artifacts.single.expectedMediaId, mediaId);
        expect(artifacts.single.createdUtc, '2026-09-09T12:00:00Z');
        expect(backend.paths, [
          '/api/gateway-grants/bulletin-media-runs',
          '/api/gateway-grants/bulletin-media-artifacts'
        ]);
        expect(backend.requestBodies.first.containsKey('limit'), isFalse);
        for (final body in backend.requestBodies) {
          final encoded = jsonEncode(body);
          expect(encoded, isNot(contains('run_root')));
          expect(encoded, isNot(contains('state_root')));
          expect(encoded, isNot(contains('artifact_root')));
          expect(encoded, isNot(contains('source_path')));
          expect(encoded, isNot(contains('stored_path')));
        }
      } finally {
        client.close();
        await backend.close();
      }
    }

    await exercise('run_20260909T000000_alpha', 'alpha root fixture');
    await exercise('run_20260909T000000_beta', 'beta root fixture');
  });

  test('proposal-only backend response is previewable but not dispatchable',
      () {
    final response = BulletinMediaPreviewResponse.fromJson(proposalJson());

    expect(response.review.invalidResponse, isFalse);
    expect(response.canDispatch, isFalse);
    expect(response.parseIssues.map((i) => i.field), contains('operation'));
  });

  test('mismatched prepared operation is never dispatchable', () {
    final response = BulletinMediaPreviewResponse.fromJson(
        previewResponseJson(clientRequestId: 'bulletin_media_request_002'));

    expect(response.canDispatch, isFalse);
    expect(response.parseIssues.map((i) => i.field), contains('operation'));
  });

  test('rejects malformed review rows and hidden local path values', () {
    final badReview = BulletinMediaReview.fromJson(reviewJson(extra: {
      'local_path': 'C:/Users/Operator/private/meme.png',
    }));
    final badArtifact = BulletinMediaArtifact.fromJson(
        artifactJson(label: 'C:/Users/Operator/private/meme.png'), 'artifact');
    final badRef = BulletinMediaReview.fromJson(
        reviewJson(ref: 'file:///C:/Users/Operator/private/meme.png'));

    expect(badReview.invalidResponse, isTrue);
    expect(badArtifact.invalidResponse, isTrue);
    expect(badArtifact.parseIssues.single.rawValue, '[redacted]');
    expect(badRef.invalidResponse, isTrue);
  });

  test('maps partial publication result states without claiming success', () {
    final partial = BulletinMediaPublishResult.fromJson(
        publishResultJson('media_uploaded_post_failed'));
    final success = BulletinMediaPublishResult.fromJson(
        publishResultJson('posted_readback_match'));

    expect(partial.invalidResponse, isFalse);
    expect(partial.state, BulletinMediaPublishState.mediaUploadedPostFailed);
    expect(partial.humanStatus, 'Media uploaded; post failed.');
    expect(partial.complete, isFalse);
    expect(success.complete, isTrue);
  });

  test('cache posts authenticated request, verifies hash, and deletes copy',
      () async {
    final dir = await Directory.systemTemp.createTemp('bulletin-cache-test');
    final bytes = tinyPngBytes();
    final digest = sha256.convert(bytes).toString();
    final item = BulletinMediaReview.fromJson(reviewJson(attachmentSha: digest))
        .items
        .single;
    final cache = BulletinMediaCache(
      baseDir: dir,
      proposalRef: proposalRef,
      previewSha256: digest,
      fetch: (path, body) async {
        expect(path, bulletinPreviewBytesPath);
        expect(body['proposal_ref'], proposalRef);
        expect(body['preview_ref'], previewRef);
        return GatewayByteResponse(
            200,
            {
              'content-type': 'image/png',
              'content-length': bytes.length.toString(),
              'x-flywheel-sha256': digest,
            },
            bytes);
      },
    );

    final handle = await cache.load(item);
    expect(handle.file.existsSync(), isTrue);
    expect(await handle.file.readAsBytes(), bytes);
    await handle.delete();
    expect(handle.file.existsSync(), isFalse);
    await dir.delete(recursive: true);
  });

  test('cache rejects redirects and wrong bytes before playback', () async {
    final dir = await Directory.systemTemp.createTemp('bulletin-cache-test');
    final item = BulletinMediaReview.fromJson(reviewJson()).items.single;
    final redirect = BulletinMediaCache(
      baseDir: dir,
      proposalRef: proposalRef,
      previewSha256: shaA,
      fetch: (_, __) async => GatewayByteResponse(302, {'location': '/'}, []),
    );
    final wrongBytes = BulletinMediaCache(
      baseDir: dir,
      proposalRef: proposalRef,
      previewSha256: shaA,
      fetch: (_, __) async => GatewayByteResponse(200, {
        'content-type': 'image/png',
        'content-length': '3',
      }, [
        1,
        2,
        3
      ]),
    );

    expect(
        () => redirect.load(item), throwsA(isA<BulletinMediaCacheException>()));
    expect(() => wrongBytes.load(item),
        throwsA(isA<BulletinMediaCacheException>()));
    await dir.delete(recursive: true);
  });

  test('cache sweeps stale app-owned preview files before writing new copy',
      () async {
    final dir = await Directory.systemTemp.createTemp('bulletin-cache-test');
    final stale = File('${dir.path}${Platform.pathSeparator}stale.mp4')
      ..writeAsBytesSync([7, 8, 9]);
    await stale.setLastModified(
        DateTime.now().toUtc().subtract(const Duration(days: 2)));
    final bytes = tinyPngBytes();
    final digest = sha256.convert(bytes).toString();
    final item = BulletinMediaReview.fromJson(reviewJson(attachmentSha: digest))
        .items
        .single;
    final cache = BulletinMediaCache(
      baseDir: dir,
      proposalRef: proposalRef,
      previewSha256: digest,
      fetch: (_, __) async => GatewayByteResponse(
          200,
          {
            'content-type': 'image/png',
            'content-length': bytes.length.toString(),
            'x-flywheel-sha256': digest,
          },
          bytes),
    );

    final handle = await cache.load(item);

    expect(stale.existsSync(), isFalse);
    expect(handle.file.existsSync(), isTrue);
    await handle.delete();
    await dir.delete(recursive: true);
  });

  test('cache sweep does not traverse nested paths or linked entries',
      () async {
    final dir = await Directory.systemTemp.createTemp('bulletin-cache-test');
    final nested = Directory('${dir.path}${Platform.pathSeparator}nested')
      ..createSync();
    final nestedStale =
        File('${nested.path}${Platform.pathSeparator}outside-sweep.mp4')
          ..writeAsBytesSync([4, 5, 6]);
    await nestedStale.setLastModified(
        DateTime.now().toUtc().subtract(const Duration(days: 2)));
    final outside = await Directory.systemTemp.createTemp('bulletin-cache-out');
    final outsideFile = File('${outside.path}${Platform.pathSeparator}keep.mp4')
      ..writeAsBytesSync([1, 2, 3]);
    final link =
        Link('${dir.path}${Platform.pathSeparator}linked-preview-cache.mp4');
    var linkCreated = false;
    try {
      await link.create(outsideFile.path);
      linkCreated = true;
    } on FileSystemException {
      linkCreated = false;
    }
    final bytes = tinyPngBytes();
    final digest = sha256.convert(bytes).toString();
    final item = BulletinMediaReview.fromJson(reviewJson(attachmentSha: digest))
        .items
        .single;
    final cache = BulletinMediaCache(
      baseDir: dir,
      proposalRef: proposalRef,
      previewSha256: digest,
      fetch: (_, __) async => GatewayByteResponse(
          200,
          {
            'content-type': 'image/png',
            'content-length': bytes.length.toString(),
            'x-flywheel-sha256': digest,
          },
          bytes),
    );

    final handle = await cache.load(item);

    expect(nestedStale.existsSync(), isTrue);
    if (linkCreated) {
      expect(outsideFile.existsSync(), isTrue);
      expect(link.existsSync(), isTrue);
    }
    await handle.delete();
    if (linkCreated) await link.delete();
    await dir.delete(recursive: true);
    await outside.delete(recursive: true);
  });
}
