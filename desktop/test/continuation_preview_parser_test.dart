import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/continuation_models.dart';

const _previewRef = 'cpv_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _shaA =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _shaB =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

Map<String, Object?> _previewJson({
  required String head,
  String previewSha256 = _shaA,
}) =>
    {
      'schema': 'flywheel.native-continuation-preview/v1',
      'preview_ref': _previewRef,
      'preview_sha256': previewSha256,
      'source_state_sha256': _shaB,
      'intake_ref': 'continuation/$_previewRef.intake.json',
      'source': {'root': r'C:\work\repo', 'export_path': null},
      'repo': {'branch': 'main', 'head': head, 'dirty_files': const []},
      'import': {
        'mappings': const [],
        'dropped': const [],
        'mcp_server_count': 0
      },
      'export': {'signals': const []},
      'context_package': {
        'selected_tasks': const [],
        'selected_summaries': const [],
        'selected_files': const [],
      },
      'runner_context': {
        'root': r'C:\work\repo',
        'goal': 'Continue with private context.',
        'selected_files': const [],
      },
      'provider_native_resume': {
        'state': 'unavailable',
        'reason': 'provider-native resume is not claimed',
      },
      'health': {'state': 'ready', 'blocking_omissions': const []},
      'omissions': const [],
    };

void main() {
  test('repo head accepts Git SHA-1 and SHA-256 object IDs', () {
    for (final head in ['a' * 40, 'b' * 64]) {
      final preview = ContinuationPreview.fromJson(_previewJson(head: head));

      expect(preview.invalidResponse, isFalse);
      expect(preview.head, head);
    }
  });

  test('preview evidence digests still reject Git SHA-1 length values', () {
    final preview = ContinuationPreview.fromJson(
      _previewJson(head: 'a' * 40, previewSha256: 'c' * 40),
    );

    expect(preview.head, 'a' * 40);
    expect(preview.invalidResponse, isTrue);
    expect(
      preview.parseIssues.map((issue) => issue.field),
      contains('preview_sha256'),
    );
  });
}
