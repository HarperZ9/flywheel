import 'dart:io';

import 'package:flutter/material.dart';

import '../models/bulletin_media_models.dart';
import '../services/bulletin_media_cache.dart';
import 'bulletin_media_player.dart';

typedef BulletinMediaPlayerBuilder = Widget Function(
    BuildContext context, CachedBulletinMedia media);

final class BulletinMediaReviewPanel extends StatefulWidget {
  final BulletinMediaReview review;
  final BulletinMediaLoader loader;
  final BulletinMediaPlayerBuilder? mediaPlayerBuilder;

  const BulletinMediaReviewPanel({
    super.key,
    required this.review,
    required this.loader,
    this.mediaPlayerBuilder,
  });

  @override
  State<BulletinMediaReviewPanel> createState() =>
      _BulletinMediaReviewPanelState();
}

final class _BulletinMediaReviewPanelState
    extends State<BulletinMediaReviewPanel> {
  final _loaded = <String, CachedBulletinMedia>{};
  final _errors = <String, String>{};
  final _loading = <String>{};

  @override
  void dispose() {
    _deleteLoaded();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant BulletinMediaReviewPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_reviewKey(oldWidget.review) != _reviewKey(widget.review)) {
      _deleteLoaded();
      _errors.clear();
      _loading.clear();
    }
  }

  void _deleteLoaded() {
    for (final media in _loaded.values) {
      media.deleteBestEffort();
    }
    _loaded.clear();
  }

  Future<void> _load(BulletinMediaPreviewItem item) async {
    final id = item.attachment.mediaId;
    setState(() {
      _loading.add(id);
      _errors.remove(id);
    });
    try {
      final media = await widget.loader.load(item);
      if (!mounted) {
        await media.delete();
        return;
      }
      setState(() => _loaded[id] = media);
    } on Object {
      if (mounted) setState(() => _errors[id] = 'Media preview failed.');
    } finally {
      if (mounted) setState(() => _loading.remove(id));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (widget.review.invalidResponse) {
      return const Text('Bulletin media review was invalid.');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Bulletin media review',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Text(widget.review.post.body),
        if (widget.review.post.altContext.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text(widget.review.post.altContext),
        ],
        const SizedBox(height: 8),
        const Text(
          'The entire selected file becomes public, including embedded metadata.',
          style: TextStyle(fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 12),
        ...widget.review.items.map(_mediaCard),
        const SizedBox(height: 12),
        Text('Effect: ${widget.review.effect}'),
        const SizedBox(height: 8),
        const Text('Does not prove:'),
        ...widget.review.doesNotProve.map((row) => Text('- $row')),
        const Divider(height: 24),
        const Text('Secondary verification details'),
        ...widget.review.items.map((item) => Text(
            '${item.attachment.label} SHA-256: ${item.attachment.sha256}',
            maxLines: 1,
            overflow: TextOverflow.ellipsis)),
        Text('Preview SHA-256: ${widget.review.previewSha256}'),
        Text('Body SHA-256: ${widget.review.bodySha256}'),
        Text('Media list SHA-256: ${widget.review.mediaListSha256}'),
      ],
    );
  }

  Widget _mediaCard(BulletinMediaPreviewItem item) {
    final attachment = item.attachment;
    final loaded = _loaded[attachment.mediaId];
    final loading = _loading.contains(attachment.mediaId);
    final error = _errors[attachment.mediaId];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(attachment.label,
              style: const TextStyle(fontWeight: FontWeight.w600)),
          Text('${attachment.kind.name} · ${attachment.mediaType} · '
              '${attachment.bytes} bytes'),
          const SizedBox(height: 4),
          Text(attachment.alt),
          const SizedBox(height: 8),
          if (loaded == null)
            FilledButton(
              onPressed: loading ? null : () => _load(item),
              child: Text(
                  loading ? 'Loading media preview' : 'Load media preview'),
            ),
          if (error != null) Text(error),
          if (loaded != null) _preview(loaded),
        ]),
      ),
    );
  }

  Widget _preview(CachedBulletinMedia media) {
    final kind = media.attachment.kind;
    if (kind == BulletinMediaKind.image) {
      return Image.file(media.file, height: 160, fit: BoxFit.contain);
    }
    return widget.mediaPlayerBuilder?.call(context, media) ??
        BulletinMediaPlayer(file: media.file, kind: kind.name);
  }
}

Future<bool> bulletinMediaFileExists(File file) => file.exists();

String _reviewKey(BulletinMediaReview review) => [
      review.previewSha256,
      for (final item in review.items)
        '${item.preview.previewRef}:${item.attachment.mediaId}:'
            '${item.attachment.sha256}'
    ].join('|');
