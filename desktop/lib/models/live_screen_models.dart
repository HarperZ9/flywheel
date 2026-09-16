/// Capture and model delivery are separate observations. A rendered preview
/// never establishes that a provider received its bytes.
library;

import 'evidence_state.dart';

enum ScreenCaptureState { stopped, starting, running, paused, disconnected }

String? _text(Object? value) => value is String &&
        value.isNotEmpty &&
        value.length <= 256 &&
        isSafePublicText(value)
    ? value
    : null;

int? _count(Object? value) =>
    value is int && value >= 0 && value <= 9007199254740991 ? value : null;

String? _digest(Object? value) =>
    value is String && RegExp(r'^[a-f0-9]{64}$').hasMatch(value) ? value : null;

String? _deliveryRef(Object? value) =>
    value is String && RegExp(r'^dlv_[a-f0-9]{32}$').hasMatch(value)
        ? value
        : null;

DateTime? _utc(Object? value) {
  if (value is! String) return null;
  final parts = RegExp(
          r'^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?Z$')
      .firstMatch(value);
  if (parts == null) return null;
  final parsed = DateTime.tryParse(value)?.toUtc();
  if (parsed == null) return null;
  final actual = [
    parsed.year,
    parsed.month,
    parsed.day,
    parsed.hour,
    parsed.minute,
    parsed.second
  ];
  for (var i = 0; i < actual.length; i++) {
    if (actual[i] != int.parse(parts.group(i + 1)!)) return null;
  }
  return parsed;
}

final class LiveScreenSource {
  const LiveScreenSource._(this.id, this.kind, this.label, this.backend,
      this.available, this.unavailableReason);
  final String id, kind, label, backend;
  final bool available;
  final String? unavailableReason;

  factory LiveScreenSource.fromJson(Map<String, Object?> json) {
    final id = _text(json['source_id']);
    final kind = _text(json['kind']);
    final label = _text(json['label']);
    final backend = _text(json['backend']);
    final valid = id != null &&
        label != null &&
        backend != null &&
        const {'display', 'window', 'region', 'synthetic'}.contains(kind);
    return LiveScreenSource._(
        id ?? '',
        kind ?? 'unknown',
        label ?? 'Unknown source',
        backend ?? 'unknown',
        valid && json['available'] == true,
        _text(json['unavailable_reason']) ??
            (valid ? null : 'Source details unavailable'));
  }
}

final class LiveScreenFrame {
  const LiveScreenFrame._(
      this.sessionId,
      this.sourceId,
      this.sequence,
      this.aggregateSequence,
      this.digest,
      this.capturedAt,
      this.width,
      this.height,
      this.valid);
  final String sessionId, sourceId, digest;
  final int sequence, aggregateSequence, width, height;
  final DateTime? capturedAt;
  final bool valid;

  factory LiveScreenFrame.fromJson(Map<String, Object?> json) {
    final session = _text(json['session_id']);
    final source = _text(json['source_id']);
    final sequence = _count(json['source_sequence']);
    final aggregate = _count(json['aggregate_sequence']);
    final digest = _digest(json['frame_sha256']);
    final captured = _utc(json['captured_at_utc']);
    final width = _count(json['width']);
    final height = _count(json['height']);
    final valid = session != null &&
        source != null &&
        sequence != null &&
        aggregate != null &&
        digest != null &&
        captured != null &&
        width != null &&
        width > 0 &&
        width <= 32768 &&
        height != null &&
        height > 0 &&
        height <= 32768;
    return LiveScreenFrame._(session ?? '', source ?? '', sequence ?? 0,
        aggregate ?? 0, digest ?? '', captured, width ?? 0, height ?? 0, valid);
  }
}

enum ScreenDeliveryMode { perceptionText, sampledImage, nativeVideo, unknown }

final class LiveScreenDelivery {
  const LiveScreenDelivery._(
      this.sessionId,
      this.sourceId,
      this.sequence,
      this.aggregateSequence,
      this.digest,
      this.modelRoute,
      this.model,
      this.deliveryRef,
      this.deliveryReceiptSha256,
      this.mode,
      this.deliveredAt,
      this.frameAgeMs,
      this.stale,
      this.valid);
  final String sessionId, sourceId, digest, modelRoute, model;
  final String deliveryRef, deliveryReceiptSha256;
  final int sequence, aggregateSequence, frameAgeMs;
  final ScreenDeliveryMode mode;
  final DateTime? deliveredAt;
  final bool stale, valid;

  factory LiveScreenDelivery.fromJson(Map<String, Object?> json) {
    final session = _text(json['session_id']);
    final source = _text(json['source_id']);
    final sequence = _count(json['source_sequence']);
    final aggregate = _count(json['aggregate_sequence']);
    final digest = _digest(json['frame_sha256']);
    final route = _text(json['model_route']);
    final model = _text(json['model']);
    final delivered = _utc(json['delivered_at_utc']);
    final age = _count(json['frame_age_ms']);
    final rawDeliveryRef = _deliveryRef(json['delivery_ref']);
    final rawReceipt = _digest(json['delivery_receipt_sha256']);
    final deliveryRef =
        rawDeliveryRef != null && rawReceipt != null ? rawDeliveryRef : '';
    final deliveryReceiptSha256 =
        rawDeliveryRef != null && rawReceipt != null ? rawReceipt : '';
    final mode = switch (json['delivery_mode']) {
      'perception_text' => ScreenDeliveryMode.perceptionText,
      'sampled_image' => ScreenDeliveryMode.sampledImage,
      'native_video' => ScreenDeliveryMode.nativeVideo,
      _ => ScreenDeliveryMode.unknown,
    };
    final nested = json['frame'];
    final identityMatches = nested is Map &&
        nested.length == 5 &&
        nested['session_id'] == session &&
        nested['source_id'] == source &&
        nested['source_sequence'] == sequence &&
        nested['aggregate_sequence'] == aggregate &&
        nested['frame_sha256'] == digest;
    final valid = identityMatches &&
        session != null &&
        source != null &&
        sequence != null &&
        aggregate != null &&
        digest != null &&
        route != null &&
        model != null &&
        delivered != null &&
        age != null &&
        age <= 86400000 &&
        json['stale'] is bool &&
        mode != ScreenDeliveryMode.unknown;
    return LiveScreenDelivery._(
        session ?? '',
        source ?? '',
        sequence ?? 0,
        aggregate ?? 0,
        digest ?? '',
        route ?? '',
        model ?? '',
        deliveryRef,
        deliveryReceiptSha256,
        mode,
        delivered,
        age ?? 0,
        json['stale'] != false,
        valid);
  }

  bool get hasDeliveryReceiptRef =>
      deliveryRef.isNotEmpty && deliveryReceiptSha256.isNotEmpty;

  bool matches(LiveScreenFrame frame) =>
      valid &&
      frame.valid &&
      sessionId == frame.sessionId &&
      sourceId == frame.sourceId &&
      sequence == frame.sequence &&
      aggregateSequence == frame.aggregateSequence &&
      digest == frame.digest;

  /// Ages the provider delivery receipt, not the newest local preview.
  /// A negative elapsed time is an unknown clock relationship.
  Duration? ageAt(DateTime now) {
    final delivered = deliveredAt;
    if (!valid || delivered == null || now.isBefore(delivered)) return null;
    return Duration(milliseconds: frameAgeMs) + now.difference(delivered);
  }

  String get modeLabel => switch (mode) {
        ScreenDeliveryMode.perceptionText => 'Measured text',
        ScreenDeliveryMode.sampledImage => 'Selected frames',
        ScreenDeliveryMode.nativeVideo => 'Native video',
        ScreenDeliveryMode.unknown => 'Delivery mode unavailable',
      };
}
