import 'evidence_state.dart';

const bulletinPublicationSchema = 'flywheel.outcome-bulletin-publication/v1';
const bulletinResultSchema = 'flywheel.outcome-bulletin-media-result/v1';

enum BulletinMediaPublishState {
  grantBindingMismatch,
  publishUnavailable,
  mediaUploadFailed,
  mediaUploadDrift,
  mediaUploadUnverified,
  mediaUploadedPostFailed,
  mediaUploadedPostUnverified,
  postedReadbackUnavailable,
  postedReadbackDrift,
  postedReadbackMatch,
  invalidResponse,
}

const _states = {
  'grant_binding_mismatch': BulletinMediaPublishState.grantBindingMismatch,
  'publish_unavailable': BulletinMediaPublishState.publishUnavailable,
  'media_upload_failed': BulletinMediaPublishState.mediaUploadFailed,
  'media_upload_drift': BulletinMediaPublishState.mediaUploadDrift,
  'media_upload_unverified': BulletinMediaPublishState.mediaUploadUnverified,
  'media_uploaded_post_failed':
      BulletinMediaPublishState.mediaUploadedPostFailed,
  'media_uploaded_post_unverified':
      BulletinMediaPublishState.mediaUploadedPostUnverified,
  'posted_readback_unavailable':
      BulletinMediaPublishState.postedReadbackUnavailable,
  'posted_readback_drift': BulletinMediaPublishState.postedReadbackDrift,
  'posted_readback_match': BulletinMediaPublishState.postedReadbackMatch,
};

final class BulletinMediaPublishResult extends DefensiveModel {
  final BulletinMediaPublishState state;
  final String rawState, postRef, message;
  final List<String> mediaIds;
  BulletinMediaPublishResult._(this.state, this.rawState, this.postRef,
      this.message, this.mediaIds, super.parseIssues);

  bool get complete => state == BulletinMediaPublishState.postedReadbackMatch;

  String get humanStatus => switch (state) {
        BulletinMediaPublishState.grantBindingMismatch =>
          'Grant binding mismatch; no upload attempted.',
        BulletinMediaPublishState.publishUnavailable =>
          'Publish unavailable; no upload attempted.',
        BulletinMediaPublishState.mediaUploadFailed =>
          'Media upload failed; post was not attempted.',
        BulletinMediaPublishState.mediaUploadDrift =>
          'Media upload drift; post was not attempted.',
        BulletinMediaPublishState.mediaUploadUnverified =>
          'Media upload unverified; post was not attempted.',
        BulletinMediaPublishState.mediaUploadedPostFailed =>
          'Media uploaded; post failed.',
        BulletinMediaPublishState.mediaUploadedPostUnverified =>
          'Media uploaded; post result unverified.',
        BulletinMediaPublishState.postedReadbackUnavailable =>
          'Post readback unavailable.',
        BulletinMediaPublishState.postedReadbackDrift => 'Post readback drift.',
        BulletinMediaPublishState.postedReadbackMatch =>
          'Posted readback matched.',
        BulletinMediaPublishState.invalidResponse =>
          'Publication result was invalid.',
      };

  factory BulletinMediaPublishResult.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    final schema = json['schema'];
    if (schema != bulletinPublicationSchema && schema != bulletinResultSchema) {
      addParseIssue(issues, 'schema', schema);
    }
    final raw = json['status'] ?? json['state'];
    final state = _states[raw] ?? BulletinMediaPublishState.invalidResponse;
    if (state == BulletinMediaPublishState.invalidResponse) {
      addParseIssue(issues, 'state', raw);
    }
    return BulletinMediaPublishResult._(
      state,
      safeRawValue(raw) ?? '',
      readText(json, 'post_id', issues, optional: true).isNotEmpty
          ? readText(json, 'post_id', issues, optional: true)
          : readText(json, 'post_ref', issues, optional: true),
      readText(json, 'message', issues, optional: true),
      readStringList(json['media_ids'] ?? const [], 'media_ids', issues),
      issues,
    );
  }
}
