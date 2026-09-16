import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/live_screen_models.dart';

void main() {
  final captured = DateTime.utc(2026, 9, 15, 10);
  final frameJson = <String, Object?>{
    'session_id': 'session-a',
    'source_id': 'display:primary',
    'source_sequence': 4,
    'aggregate_sequence': 6,
    'captured_at_utc': captured.toIso8601String(),
    'frame_sha256': 'a' * 64,
    'width': 1920,
    'height': 1080,
  };
  final deliveryJson = <String, Object?>{
    'session_id': 'session-a',
    'source_id': 'display:primary',
    'source_sequence': 4,
    'aggregate_sequence': 6,
    'frame': {
      'session_id': 'session-a',
      'source_id': 'display:primary',
      'source_sequence': 4,
      'aggregate_sequence': 6,
      'frame_sha256': 'a' * 64,
    },
    'frame_sha256': 'a' * 64,
    'model_route': 'selected-route',
    'model': 'vision-model',
    'delivery_mode': 'sampled_image',
    'delivered_at_utc':
        captured.add(const Duration(seconds: 2)).toIso8601String(),
    'frame_age_ms': 2000,
    'stale': false,
  };

  test('a valid preview does not establish model delivery', () {
    final frame = LiveScreenFrame.fromJson(frameJson);
    expect(frame.valid, isTrue);
    expect(LiveScreenDelivery.fromJson({}).valid, isFalse);
  });

  test('delivery binds session, source, sequence and bytes', () {
    final frame = LiveScreenFrame.fromJson(frameJson);
    final delivery = LiveScreenDelivery.fromJson(deliveryJson);
    expect(delivery.matches(frame), isTrue);
    for (final change in [
      {'session_id': 'session-b'},
      {'source_id': 'display:other'},
      {'source_sequence': 5},
      {'aggregate_sequence': 7},
      {'frame_sha256': 'b' * 64},
    ]) {
      expect(
          LiveScreenDelivery.fromJson({...deliveryJson, ...change})
              .matches(frame),
          isFalse);
    }
  });

  test('delivered observation ages even when no new frame arrives', () {
    final delivery = LiveScreenDelivery.fromJson(deliveryJson);
    expect(delivery.ageAt(captured.add(const Duration(seconds: 7))),
        const Duration(seconds: 7));
    expect(delivery.ageAt(captured), isNull,
        reason: 'clock disagreement cannot produce a fresh-view claim');
  });

  test('unsupported modes and malformed evidence remain unavailable', () {
    for (final change in [
      {'delivery_mode': 'vision-ish'},
      {'frame_age_ms': -1},
      {'frame_age_ms': 1.5},
      {'source_sequence': true},
      {'frame_sha256': 'not-a-digest'},
      {'delivered_at_utc': '2026-09-15T10:00:00'},
      {'delivered_at_utc': '2026-02-30T10:00:00Z'},
      {'delivered_at_utc': '2026-09-15T25:00:00Z'},
      {'delivered_at_utc': '2026-09-15T10:00:60Z'},
      {'stale': 'false'},
      {'frame': null},
      {
        'frame': {'session_id': 'other'}
      },
    ]) {
      expect(LiveScreenDelivery.fromJson({...deliveryJson, ...change}).valid,
          isFalse);
    }
  });

  test('conflicting nested frame cannot establish model delivery', () {
    final identity = Map<String, Object?>.from(deliveryJson['frame'] as Map);
    for (final change in [
      {'session_id': 'other'},
      {'source_id': 'other'},
      {'source_sequence': 9},
      {'aggregate_sequence': 9},
      {'frame_sha256': 'b' * 64},
    ]) {
      final receipt = LiveScreenDelivery.fromJson({
        ...deliveryJson,
        'frame': {...identity, ...change},
      });
      expect(receipt.valid, false);
      expect(receipt.matches(LiveScreenFrame.fromJson(frameJson)), false);
    }
  });

  test('delivery preserves exact provider delivery receipt references', () {
    final delivery = LiveScreenDelivery.fromJson({
      ...deliveryJson,
      'delivery_ref': 'dlv_${'1' * 32}',
      'delivery_receipt_sha256': 'b' * 64,
    });

    expect(delivery.valid, isTrue);
    expect(delivery.deliveryRef, 'dlv_${'1' * 32}');
    expect(delivery.deliveryReceiptSha256, 'b' * 64);
    expect(delivery.hasDeliveryReceiptRef, isTrue);
  });

  test('malformed optional delivery refs are not exposed as authority refs',
      () {
    for (final change in [
      {'delivery_ref': 'delivery-1', 'delivery_receipt_sha256': 'b' * 64},
      {'delivery_ref': 'dlv_${'1' * 31}', 'delivery_receipt_sha256': 'b' * 64},
      {
        'delivery_ref': 'dlv_${'1' * 32}',
        'delivery_receipt_sha256': 'not-a-sha'
      },
      {'delivery_ref': 'dlv_${'1' * 32}'},
      {'delivery_receipt_sha256': 'b' * 64},
      {'delivery_ref': 5, 'delivery_receipt_sha256': 'b' * 64},
    ]) {
      final delivery =
          LiveScreenDelivery.fromJson({...deliveryJson, ...change});
      expect(delivery.valid, isTrue);
      expect(delivery.deliveryRef, isEmpty);
      expect(delivery.deliveryReceiptSha256, isEmpty);
      expect(delivery.hasDeliveryReceiptRef, isFalse);
    }
  });

  test('source availability requires explicit boolean and known kind', () {
    const source = {
      'source_id': 'display:primary',
      'kind': 'display',
      'label': 'Primary display',
      'backend': 'gdi',
      'available': true,
    };
    expect(LiveScreenSource.fromJson(source).available, isTrue);
    expect(
        LiveScreenSource.fromJson({...source, 'available': 'true'}).available,
        isFalse);
    expect(LiveScreenSource.fromJson({...source, 'kind': 'other'}).available,
        isFalse);
  });
}
