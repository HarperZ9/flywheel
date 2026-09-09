import 'evidence_state.dart';

const bulletinMediaReviewSchema = 'flywheel.bulletin-media-review/v1';
final _previewRef = RegExp(r'^data_bulletin_media_preview_[0-9a-f]{16,64}$');
final _mediaId = RegExp(r'^[A-Za-z0-9_-]{16,128}$');
final bulletinMediaTypePattern =
    RegExp(r'^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$');
final _room = RegExp(r'^[a-z0-9][a-z0-9-]{0,63}$');

void bulletinExact(Map<String, Object?> value, Set<String> fields,
    List<ParseIssue> issues, String field) {
  if (value.keys.toSet().length != fields.length ||
      !value.keys.every(fields.contains)) {
    addParseIssue(issues, field, null);
  }
}

int bulletinReadNonNegativeInt(
    Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final raw = json[field];
  if (raw is int && raw >= 0) return raw;
  addParseIssue(issues, field, raw);
  return 0;
}

Uri _readBaseUrl(Map<String, Object?> json, List<ParseIssue> issues) {
  final fields = {
    'base_url',
    if (json.containsKey('hash')) 'hash',
    if (json.containsKey('base_url_sha256')) 'base_url_sha256'
  };
  bulletinExact(json, fields, issues, 'destination');
  final raw = json['base_url'];
  final value = raw is String && isSafePublicBaseUrl(raw) ? raw : '';
  final parsed = Uri.tryParse(value);
  if (parsed == null) {
    addParseIssue(issues, 'base_url', raw);
    return Uri();
  }
  if (json.containsKey('hash')) {
    readText(json, 'hash', issues, pattern: sha256Pattern);
  }
  if (json.containsKey('base_url_sha256')) {
    readText(json, 'base_url_sha256', issues, pattern: sha256Pattern);
  }
  return parsed;
}

enum BulletinMediaKind { image, audio, video, invalidResponse }

BulletinMediaKind bulletinMediaKind(
    Object? raw, String field, List<ParseIssue> issues) {
  const values = {
    'image': BulletinMediaKind.image,
    'audio': BulletinMediaKind.audio,
    'video': BulletinMediaKind.video,
  };
  final parsed = values[raw];
  if (parsed != null) return parsed;
  addParseIssue(issues, field, raw);
  return BulletinMediaKind.invalidResponse;
}

final class BulletinMediaPost extends DefensiveModel {
  final String room, title, body, altContext;
  BulletinMediaPost._(
      this.room, this.title, this.body, this.altContext, super.parseIssues);

  factory BulletinMediaPost.fromJson(Map<String, Object?> json, String field) {
    final issues = <ParseIssue>[];
    final fields = {
      'room',
      'body',
      if (json.containsKey('title')) 'title',
      if (json.containsKey('alt_context')) 'alt_context'
    };
    bulletinExact(json, fields, issues, field);
    return BulletinMediaPost._(
      readText(json, 'room', issues, pattern: _room),
      readText(json, 'title', issues, optional: true),
      readText(json, 'body', issues),
      readText(json, 'alt_context', issues, optional: true),
      issues,
    );
  }
}

final class BulletinMediaAttachment extends DefensiveModel {
  final String mediaId, label, mediaType, sha256, alt;
  final int bytes;
  final BulletinMediaKind kind;
  BulletinMediaAttachment._(this.mediaId, this.label, this.kind, this.mediaType,
      this.bytes, this.sha256, this.alt, super.parseIssues);

  factory BulletinMediaAttachment.fromJson(
      Map<String, Object?> json, String field) {
    final issues = <ParseIssue>[];
    final fields = {
      'media_id',
      'label',
      'kind',
      'media_type',
      'bytes',
      'sha256',
      'alt',
      if (json.containsKey('artifact_id')) 'artifact_id',
      if (json.containsKey('expected_media_id')) 'expected_media_id',
      if (json.containsKey('preview_ref')) 'preview_ref'
    };
    bulletinExact(json, fields, issues, field);
    return BulletinMediaAttachment._(
      readText(json, 'media_id', issues, pattern: _mediaId).isNotEmpty
          ? readText(json, 'media_id', issues, pattern: _mediaId)
          : readText(json, 'expected_media_id', issues, pattern: _mediaId),
      readText(json, 'label', issues),
      bulletinMediaKind(json['kind'], '$field.kind', issues),
      readText(json, 'media_type', issues, pattern: bulletinMediaTypePattern),
      bulletinReadNonNegativeInt(json, 'bytes', issues),
      readText(json, 'sha256', issues, pattern: sha256Pattern),
      readText(json, 'alt', issues),
      issues,
    );
  }
}

final class BulletinPreviewMedia extends DefensiveModel {
  final String mediaId, previewRef, mediaType;
  final int bytes;
  final BulletinMediaKind kind;
  BulletinPreviewMedia._(this.mediaId, this.previewRef, this.kind,
      this.mediaType, this.bytes, super.parseIssues);

  factory BulletinPreviewMedia.fromJson(Map<String, Object?> json, String f) {
    final issues = <ParseIssue>[];
    bulletinExact(
        json,
        const {'media_id', 'preview_ref', 'kind', 'media_type', 'bytes'},
        issues,
        f);
    return BulletinPreviewMedia._(
      readText(json, 'media_id', issues, pattern: _mediaId).isNotEmpty
          ? readText(json, 'media_id', issues, pattern: _mediaId)
          : readText(json, 'expected_media_id', issues, pattern: _mediaId),
      readText(json, 'preview_ref', issues, pattern: _previewRef),
      bulletinMediaKind(json['kind'], '$f.kind', issues),
      readText(json, 'media_type', issues, pattern: bulletinMediaTypePattern),
      bulletinReadNonNegativeInt(json, 'bytes', issues),
      issues,
    );
  }
}

final class BulletinMediaPreviewItem {
  final BulletinMediaAttachment attachment;
  final BulletinPreviewMedia preview;
  const BulletinMediaPreviewItem(this.attachment, this.preview);
}

final class BulletinMediaReview extends DefensiveModel {
  final String mode, effect, previewSha256;
  final String bodySha256, postPayloadSha256, mediaListSha256, packetSha256;
  final Uri destinationBaseUrl;
  final BulletinMediaPost post;
  final List<BulletinMediaAttachment> attachments;
  final List<BulletinPreviewMedia> previewMedia;
  final List<BulletinMediaPreviewItem> items;
  final List<String> doesNotProve;

  BulletinMediaReview._(
      this.mode,
      this.destinationBaseUrl,
      this.effect,
      this.post,
      this.attachments,
      this.previewMedia,
      this.items,
      this.previewSha256,
      this.bodySha256,
      this.postPayloadSha256,
      this.mediaListSha256,
      this.packetSha256,
      this.doesNotProve,
      super.parseIssues);

  factory BulletinMediaReview.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    bulletinExact(
        json,
        const {
          'schema',
          'mode',
          'destination',
          'effect',
          'post',
          'attachments',
          'preview_media',
          'does_not_prove',
          'preview_sha256',
          'body_sha256',
          'post_payload_sha256',
          'media_list_sha256',
          'packet_sha256'
        },
        issues,
        'review');
    expectSchema(json, bulletinMediaReviewSchema, issues);
    Uri destination;
    if (json['destination'] is Map<String, Object?>) {
      destination =
          _readBaseUrl(json['destination'] as Map<String, Object?>, issues);
    } else {
      addParseIssue(issues, 'destination', json['destination']);
      destination = Uri();
    }
    final post = json['post'] is Map<String, Object?>
        ? BulletinMediaPost.fromJson(
            json['post'] as Map<String, Object?>, 'post')
        : BulletinMediaPost.fromJson(const {}, 'post');
    issues.addAll(post.parseIssues);
    final attachments = readRecords(json['attachments'], 'attachments', issues,
        (row, field) => BulletinMediaAttachment.fromJson(row, field));
    final previews = readRecords(json['preview_media'], 'preview_media', issues,
        (row, field) => BulletinPreviewMedia.fromJson(row, field));
    for (final row in [...attachments, ...previews]) {
      issues.addAll(row.parseIssues);
    }
    final items = <BulletinMediaPreviewItem>[];
    for (final attachment in attachments) {
      final matches = previews.where((p) => p.mediaId == attachment.mediaId);
      if (matches.length != 1 || matches.single.kind != attachment.kind) {
        addParseIssue(issues, 'preview_media', attachment.mediaId);
      } else {
        items.add(BulletinMediaPreviewItem(attachment, matches.single));
      }
    }
    if (items.length != previews.length) {
      addParseIssue(issues, 'attachments', null);
    }
    return BulletinMediaReview._(
      readText(json, 'mode', issues),
      destination,
      readText(json, 'effect', issues),
      post,
      attachments,
      previews,
      List.unmodifiable(items),
      readText(json, 'preview_sha256', issues, pattern: sha256Pattern),
      readText(json, 'body_sha256', issues, pattern: sha256Pattern),
      readText(json, 'post_payload_sha256', issues, pattern: sha256Pattern),
      readText(json, 'media_list_sha256', issues, pattern: sha256Pattern),
      readText(json, 'packet_sha256', issues, pattern: sha256Pattern),
      readStringList(json['does_not_prove'], 'does_not_prove', issues),
      issues,
    );
  }
}
