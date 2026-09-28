import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/gateway_grant_models.dart';

const _sha = '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';
const _ref = 'data_inspect.source:0123456789abcdef0123456789abcdef';

GatewayOperation _op(Map<String, Object?> operation) => GatewayOperation.exact(
      action: 'import.inspect',
      clientRequestId: 'request-1',
      operation: operation,
    );

Map<String, Object?> _operation({Object? length = 123, Object? filename}) => {
      'source': {
        'kind': 'client-upload',
        'format': 'inspect-json',
        'sha256': _sha,
        'byte_length': length,
        if (filename != null) 'filename': filename,
      },
    };

void main() {
  test('inspect import names the exact upload destination and write scope', () {
    final op = _op(_operation(filename: 'run.json'));
    expect(op.destination.kind, 'import');
    expect(op.destination.ref, 'inspect-json:0123456789abcdef');
    expect(op.scopes, ['write']);
  });

  test('inspect import binds source metadata to the exact data ref', () {
    final op = _op({
      ..._operation(),
      'data_refs': [_ref],
      'credential_refs': <String>[],
    });
    expect(op.dataRefs, [_ref]);
    expect(op.credentialRefs, isEmpty);
  });

  test('inspect import refuses paths, mismatched refs, and bad lengths', () {
    for (final bad in [
      {
        'source': {
          'kind': 'gateway-path',
          'format': 'inspect-json',
          'sha256': _sha,
          'byte_length': 123,
        },
      },
      _operation(length: 0),
      _operation(filename: r'C:\tmp\run.json'),
      {
        ..._operation(),
        'data_refs': ['data_other']
      },
    ]) {
      expect(() => _op(bad), throwsA(isA<ArgumentError>()));
    }
  });
}
