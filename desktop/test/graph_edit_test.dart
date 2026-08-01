// The editable creative graph's authoring rules, proven without a gateway:
// arity governs runnability, wiring can never form a cycle, and the spec
// it emits matches what the engine's run_graph expects.
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/graph_edit.dart';

void main() {
  test('arity is fixed per op family', () {
    expect(arityOf('plate'), 0);
    expect(arityOf('field'), 0);
    expect(arityOf('dither'), 1);
    expect(arityOf('film_frame'), 1);
    expect(arityOf('blend'), 2);
    expect(arityOf('difference'), 2);
  });

  test('an empty graph, then a lone source, then a wired transform', () {
    final g = GraphEdit();
    expect(g.whyNotRunnable(), contains('source'));
    final src = g.add('plate');
    expect(g.whyNotRunnable(), isNull); // a lone source is a runnable graph
    final d = g.add('dither');
    expect(g.whyNotRunnable(), contains(d.id)); // dither wants 1 input
    d.inputs.add(src.id);
    expect(g.whyNotRunnable(), isNull);
  });

  test('candidate inputs never include a node that depends on this one', () {
    final g = GraphEdit();
    final a = g.add('plate');
    final d = g.add('dither')..inputs.add(a.id);
    // m already consumes d, so d must not be offered m as an input: that
    // would close a cycle.
    final m = g.add('beside')..inputs.add(d.id);
    expect(g.candidateInputs(m), contains(a.id));
    expect(g.candidateInputs(d), isNot(contains(m.id)));
    // and a node can never take itself
    expect(g.candidateInputs(a), isNot(contains(a.id)));
  });

  test('removing a node also severs edges into it', () {
    final g = GraphEdit();
    final a = g.add('plate');
    final d = g.add('dither')..inputs.add(a.id);
    g.remove(a.id);
    expect(g.byId(a.id), isNull);
    expect(d.inputs, isEmpty); // the dangling edge is gone, not orphaned
  });

  test('the emitted spec is the engine node/edge shape', () {
    final g = GraphEdit();
    final a = g.add('plate');
    final b = g.add('plate')..seed = 59;
    final m = g.add('difference')
      ..inputs.addAll([a.id, b.id]);
    final nodes = g.toNodes(96, 64);
    final edges = g.toEdges();
    expect(nodes.first['op'], 'plate');
    expect(nodes.first['args']['seed'], 58);
    expect(nodes[1]['args']['seed'], 59);
    expect(edges, containsAll([
      {'from': a.id, 'to': m.id},
      {'from': b.id, 'to': m.id},
    ]));
  });
}
