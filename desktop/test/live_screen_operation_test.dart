import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/live_screen_operation.dart';

void main() {
  test('capture review binds monitors, exact model, expiry and standard refs',
      () {
    final sources = ['display:0', 'display:1'];
    final op = openLiveScreenOperation(
        requestId: 'req-1',
        bodySessionRef: 'studio-1',
        instrumentRef: 'screen',
        sourceIds: sources,
        destination: 'openai-responses',
        model: 'vision/model-1');
    sources.clear();
    expect(op.scopes, ['write']);
    expect(op.credentialRefs, isEmpty);
    expect(op.operation['credential_refs'], isEmpty);
    expect(op.operation['data_refs'], isEmpty);
    expect(op.destination.ref, 'open:openai-responses:vision/model-1');
    expect(op.operation['sources'], hasLength(2));
    expect(op.operation['expires_after_ms'], 120000);
  });
  test('each control review names its own capture session and action', () {
    for (final action in ['start', 'pause', 'resume', 'stop']) {
      final op = controlLiveScreenOperation(
          requestId: 'req-1', sessionId: 'session-1', control: action);
      expect(op.destination.ref, 'session:session-1:$action');
      expect(op.operation['session_id'], 'session-1');
      expect(op.scopes, ['write']);
    }
  });
  test('unknown controls and duplicate or unsafe sources cannot be approved',
      () {
    expect(
        () => controlLiveScreenOperation(
            requestId: 'req-1', sessionId: 'session-1', control: 'deliver'),
        throwsArgumentError);
    for (final ids in [
      <String>[],
      ['display:0', 'display:0'],
      ['../x']
    ]) {
      expect(
          () => openLiveScreenOperation(
              requestId: 'req-1',
              bodySessionRef: 'studio-1',
              instrumentRef: 'screen',
              sourceIds: ids,
              destination: 'route-1',
              model: 'model-1'),
          throwsArgumentError);
    }
  });
}
