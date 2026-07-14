// Uplift + Science models: intervals and verdicts arrive computed by the
// engine and render as-is; includes_zero is the honest null and must
// survive parsing. Offline states name the command, like every surface.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/science_models.dart';
import 'package:flywheel_desktop/models/uplift_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/feeds_view.dart';
import 'package:flywheel_desktop/views/science_view.dart';
import 'package:flywheel_desktop/views/uplift_view.dart';

void main() {
  test('UpliftSummary parses runs, arms, and honest-null deltas', () {
    final s = UpliftSummary.fromJson({
      'runs': [
        {
          'path': 'uplift_hard.json',
          'comparison_key': 'uplift:hard_v2',
          'providers': ['ollama:qwen2.5:7b'],
          'deltas': [],
        }
      ],
      'latest': {
        'comparison_key': 'uplift:hard_v2',
        'n_candidates': 3,
        'rows': [
          {
            'provider': 'ollama:qwen2.5:7b',
            'arm': 'wrapped',
            'passes': 9,
            'graded': 10,
            'unverifiable': 0,
            'pass_rate': 0.9,
            'wilson_95': [0.596, 0.982],
            'latency_ms_mean': 3800.0,
            'candidates_mean': 1.2,
          }
        ],
        'deltas': [
          {
            'provider': 'ollama:qwen2.5:7b',
            'uplift': 0.1,
            'newcombe_95': [-0.236, 0.42],
            'includes_zero': true,
            'latency_overhead_ms': -300.0,
            'note': 'no uplift claimed: the interval includes zero',
          }
        ],
      },
    });
    expect(s.runs, hasLength(1));
    expect(s.latest, isNotNull);
    final row = s.latest!.rows.single;
    expect(row.arm, 'wrapped');
    expect(row.wilsonLo, 0.596);
    final d = s.latest!.deltas.single;
    expect(d.includesZero, isTrue);
    expect(d.verdict, 'unverifiable'); // honest null renders as unverifiable
    expect(d.note, contains('no uplift'));
  });

  test('ScienceRun parses sources, verdicts, and named stage errors', () {
    final r = ScienceRun.fromJson({
      'question': 'q',
      'sources': [
        {'id': '2603.06713', 'title': 'Scaling', 'url': 'https://x'},
      ],
      'prp': {'confidence': 6, 'validation_gates': []},
      'verdicts': [
        {'claim_id': 'c1', 'status': 'UNVERIFIABLE',
         'grounds': 'no measurement'},
      ],
      'crucible': 'seal',
      'errors': {'gather': 'HTTP 429'},
      'chain_hash': 'abc123',
    });
    expect(r.sources.single.id, '2603.06713');
    expect(r.verdicts.single.verdict, 'unverifiable');
    expect(r.errors['gather'], contains('429'));
    expect(r.plan, isNotNull);
    expect(r.plan!.confidence, 6);
  });

  for (final (name, view) in [
    ('Uplift', (GatewayClient c) => UpliftView(client: c, alive: false)),
    ('Science', (GatewayClient c) => ScienceView(client: c, alive: false)),
    ('Feeds', (GatewayClient c) => FeedsView(client: c, alive: false)),
  ]) {
    testWidgets('$name view offline names the command', (tester) async {
      await tester.pumpWidget(MaterialApp(
          theme: flywheelLightTheme(),
          home: view(GatewayClient())));
      await tester.pump();
      expect(find.textContaining('flywheel up'), findsOneWidget);
    });
  }
}
