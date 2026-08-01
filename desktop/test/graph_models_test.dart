// KnowledgeGraph models: defensive parsing, priority carried as-is (the
// engine computes it; the client never re-scores), and the context plan's
// exclusion count stays visible.
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/graph_models.dart';

void main() {
  test('KnowledgeGraph parses nodes, edges, and the context plan', () {
    final g = KnowledgeGraph.fromJson({
      'schema': 'flywheel.knowledge-graph/v1',
      'nodes': [
        {
          'id': 'hub:flywheel',
          'kind': 'hub',
          'label': 'flywheel',
          'verdict': 'live',
          'priority': 2.0,
          'cost': 50,
          'signals': {},
        },
        {
          'id': 'lane:gather',
          'kind': 'lane',
          'label': 'gather',
          'verdict': 'live',
          'priority': 1.7,
          'cost': 200,
          'signals': {'status': 'live'},
        },
      ],
      'edges': [
        {'from': 'hub:flywheel', 'to': 'lane:gather', 'kind': 'surface'},
      ],
      'context_plan': {
        'budget': 2000,
        'spent': 250,
        'selected': [
          {'id': 'hub:flywheel', 'kind': 'hub', 'label': 'flywheel'},
        ],
        'excluded': 1,
      },
    });
    expect(g.nodes, hasLength(2));
    expect(g.nodes.first.kind, 'hub');
    expect(g.nodes.last.priority, 1.7);
    expect(g.nodes.last.signals['status'], 'live');
    expect(g.edges.single.from, 'hub:flywheel');
    expect(g.plan, isNotNull);
    expect(g.plan!.excluded, 1);
    expect(g.plan!.selectedIds, contains('hub:flywheel'));
  });

  test('KnowledgeGraph degrades on an empty document', () {
    final g = KnowledgeGraph.fromJson(const {});
    expect(g.nodes, isEmpty);
    expect(g.edges, isEmpty);
    expect(g.plan, isNull);
  });
}
