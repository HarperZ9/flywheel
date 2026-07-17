// graph_edit.dart — the editable creative graph: the authoring model behind
// the node canvas. Ops carry a fixed arity, so the model can tell a valid
// wiring from an invalid one before a run is ever sent, and can name the
// exact reason a graph is not runnable. All of this is pure and testable
// without a gateway; the widget only renders and mutates it.

/// The op catalog, grouped by arity. Sources start a branch (0 inputs),
/// transforms bend one, merges join two. Kept in lockstep with the engine's
/// creative_graph.py SOURCES / TRANSFORMS / MERGES.
const graphSources = ['plate', 'wireframe', 'harmonograph', 'field'];
const graphTransforms = ['dither', 'pixel_sort', 'film_frame'];
const graphMerges = ['blend', 'beside', 'difference', 'multiply'];

int arityOf(String op) {
  if (graphMerges.contains(op)) return 2;
  if (graphTransforms.contains(op)) return 1;
  return 0; // sources
}

class GraphNodeEdit {
  final String id;
  String op;
  int seed;
  final List<String> inputs; // upstream node ids, length must equal arityOf(op)

  GraphNodeEdit({required this.id, required this.op, this.seed = 58})
      : inputs = [];

  Map<String, dynamic> toNodeJson(int width, int height) {
    final args = <String, dynamic>{};
    if (graphSources.contains(op)) {
      args['seed'] = seed;
      args['width'] = width;
      args['height'] = height;
      if (op == 'wireframe') args['primitive'] = 'orbit-sphere';
    } else if (op == 'film_frame') {
      args['seed'] = seed;
      args['grain'] = 0.4;
    }
    return {'id': id, 'op': op, 'args': args};
  }
}

class GraphEdit {
  final List<GraphNodeEdit> nodes = [];
  int _seq = 0;

  String _mint(String op) {
    final base = op.substring(0, op.length >= 3 ? 3 : op.length);
    return '$base${_seq++}';
  }

  GraphNodeEdit add(String op) {
    final n = GraphNodeEdit(id: _mint(op), op: op);
    nodes.add(n);
    return n;
  }

  void remove(String id) {
    nodes.removeWhere((n) => n.id == id);
    for (final n in nodes) {
      n.inputs.removeWhere((u) => u == id);
    }
  }

  GraphNodeEdit? byId(String id) {
    for (final n in nodes) {
      if (n.id == id) return n;
    }
    return null;
  }

  /// The ids a node may legally take as an input: any other node that does
  /// not (transitively) depend on it, so wiring can never introduce a cycle.
  List<String> candidateInputs(GraphNodeEdit node) {
    final blocked = <String>{node.id};
    var grew = true;
    while (grew) {
      grew = false;
      for (final n in nodes) {
        if (blocked.contains(n.id)) continue;
        if (n.inputs.any(blocked.contains)) {
          blocked.add(n.id);
          grew = true;
        }
      }
    }
    return [for (final n in nodes) if (!blocked.contains(n.id)) n.id];
  }

  /// Why this graph cannot run yet, or null when it is runnable. The checks
  /// mirror the engine's refusals so a run is only sent when it will succeed.
  String? whyNotRunnable() {
    if (nodes.isEmpty) return 'add a source to begin';
    for (final n in nodes) {
      final want = arityOf(n.op);
      if (n.inputs.length != want) {
        return '${n.id} (${n.op}) needs $want input'
            '${want == 1 ? '' : 's'}, has ${n.inputs.length}';
      }
    }
    if (!nodes.any((n) => graphSources.contains(n.op))) {
      return 'a graph needs at least one source';
    }
    return null;
  }

  List<Map<String, dynamic>> toNodes(int width, int height) =>
      [for (final n in nodes) n.toNodeJson(width, height)];

  List<Map<String, dynamic>> toEdges() => [
        for (final n in nodes)
          for (final u in n.inputs) {'from': u, 'to': n.id},
      ];
}
