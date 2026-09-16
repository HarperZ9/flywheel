import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/live_screen_controller.dart';
import 'package:flywheel_desktop/models/live_screen_models.dart';

void main() {
  final payload = base64Decode(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aSxkAAAAASUVORK5CYII=');
  Map<String, dynamic> frame(int seq, {String session = 'session-1'}) => {
        'event': 'screen.frame',
        'session_id': session,
        'source_id': 'display:primary',
        'source_sequence': seq,
        'aggregate_sequence': seq,
        'frame_sha256': sha256.convert(payload).toString(),
        'width': 1,
        'height': 1,
        'captured_at_utc': '2026-09-15T11:00:00Z',
      };
  http.Response imageResponse() =>
      http.Response.bytes(payload, 200, headers: {'content-type': 'image/png'});
  Future<void> flush() async {
    for (var i = 0; i < 4; i++) {
      await Future<void>.delayed(Duration.zero);
    }
  }

  final status = jsonEncode({
    'destination': 'selected-route',
    'model': 'vision-model',
    'session_id': 'session-1',
    'state': 'active',
    'source_ids': ['display:primary']
  });

  test('slow preview coalesces frames instead of queuing every image',
      () async {
    final pending = Completer<http.Response>();
    final requested = <String>[];
    final client = GatewayClient(httpClient: MockClient((req) async {
      if (!req.url.path.endsWith('/preview')) return http.Response(status, 200);
      requested.add(req.url.path);
      return requested.length == 1 ? pending.future : imageResponse();
    }));
    final controller = LiveScreenController(client);
    final shown = <int>[];
    controller.addListener(() {
      final sequence = controller.previewFrame?.sequence;
      if (sequence != null) shown.add(sequence);
    });
    final events = StreamController<Map<String, dynamic>>();
    await controller.observe('session-1', events.stream);
    events.add(frame(1));
    await flush();
    events.add(frame(2));
    events.add(frame(3));
    await flush();
    expect(requested.length, 1);
    expect(controller.previewFrame, isNull);
    pending.complete(imageResponse());
    await flush();
    expect(requested.length, 2);
    expect(requested.last, contains('/frames/3/preview'));
    expect(controller.previewFrame?.sequence, 3);
    expect(shown, contains(1),
        reason: 'continuous arrivals must not starve the completed preview');
    expect(controller.delivery, isNull);
    controller.dispose();
    await events.close();
  });

  test('stop suppresses pending preview and late active events', () async {
    final pending = Completer<http.Response>();
    var previewRequests = 0;
    final controller =
        LiveScreenController(GatewayClient(httpClient: MockClient((req) async {
      if (!req.url.path.endsWith('/preview')) return http.Response(status, 200);
      previewRequests++;
      return pending.future;
    })));
    final events = StreamController<Map<String, dynamic>>();
    await controller.observe('session-1', events.stream);
    events.add(frame(1, session: 'unrelated'));
    await flush();
    expect(previewRequests, 0);
    events.add(frame(1));
    await flush();
    expect(previewRequests, 1);
    events.add({'event': 'screen.stop', 'session_id': 'session-1'});
    events.add({
      'event': 'screen.session',
      'session_id': 'session-1',
      'state': 'active'
    });
    await flush();
    pending.complete(imageResponse());
    await flush();
    expect(controller.state, ScreenCaptureState.stopped);
    expect(controller.previewBytes, isNull);
    expect(controller.previewFrame, isNull);
    controller.dispose();
    await events.close();
  });

  test('stopped session ignores a late preview failure', () async {
    final pending = Completer<http.Response>();
    final controller = LiveScreenController(GatewayClient(
        httpClient: MockClient((req) async => req.url.path.endsWith('/preview')
            ? pending.future
            : http.Response(status, 200))));
    final events = StreamController<Map<String, dynamic>>();
    await controller.observe('session-1', events.stream);
    events.add(frame(1));
    await flush();
    events.add({'event': 'screen.stop', 'session_id': 'session-1'});
    await flush();
    pending.completeError(const FormatException('old request failed'));
    await flush();
    expect(controller.state, ScreenCaptureState.stopped);
    expect(controller.error, isNull);
    controller.dispose();
    await events.close();
  });

  test('delivery belongs to the exact session destination and model', () async {
    final controller = LiveScreenController(GatewayClient(
        httpClient: MockClient((req) async => req.url.path.endsWith('/preview')
            ? imageResponse()
            : http.Response(status, 200))));
    final events = StreamController<Map<String, dynamic>>();
    await controller.observe('session-1', events.stream);
    final observed = frame(1);
    events.add(observed);
    final receipt = {
      ...observed,
      'event': 'screen.delivery',
      'model_route': 'selected-route',
      'model': 'vision-model',
      'delivery_mode': 'sampled_image',
      'delivered_at_utc': '2026-09-15T11:00:01Z',
      'frame_age_ms': 1000,
      'stale': false,
      'frame': {
        for (final key in [
          'session_id',
          'source_id',
          'source_sequence',
          'aggregate_sequence',
          'frame_sha256'
        ])
          key: observed[key]
      },
    };
    events.add({...receipt, 'model': 'different-model'});
    events.add({...receipt, 'model_route': 'different-route'});
    await flush();
    expect(controller.delivery, isNull);
    events.add(receipt);
    await flush();
    expect(controller.delivery?.model, 'vision-model');
    expect(controller.deliveredFrame?.sequence, 1);
    controller.dispose();
    await events.close();
  });
}
