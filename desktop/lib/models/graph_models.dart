// graph_models.dart — typed reading of the cross-surface knowledge graph
// (flywheel.knowledge-graph/v1). Priority arrives computed from the named
// signals each node carries; the client renders it, never re-scores it.

/// One typed node: a surface, a project, memory, or an honest error.
class GraphNode {
  final String id;
  final String kind; // hub | lane | project | memory | plugin | workflow | error
  final String label;
  final String verdict;
  final double priority;
  final int cost;
  final Map<String, dynamic> signals;

  const GraphNode(
      {required this.id,
      required this.kind,
      required this.label,
      required this.verdict,
      required this.priority,
      required this.cost,
      required this.signals});

  factory GraphNode.fromJson(Map<String, dynamic> j) => GraphNode(
        id: j['id'] ?? '',
        kind: j['kind'] ?? '',
        label: j['label'] ?? '',
        verdict: j['verdict'] ?? '',
        priority: j['priority'] is num ? (j['priority'] as num).toDouble() : 0,
        cost: j['cost'] is num ? (j['cost'] as num).toInt() : 0,
        signals: j['signals'] is Map<String, dynamic>
            ? j['signals'] as Map<String, dynamic>
            : const {},
      );
}

class GraphEdge {
  final String from;
  final String to;
  final String kind;
  const GraphEdge({required this.from, required this.to, required this.kind});

  factory GraphEdge.fromJson(Map<String, dynamic> j) => GraphEdge(
      from: j['from'] ?? '', to: j['to'] ?? '', kind: j['kind'] ?? '');
}

/// The budgeted context plan: what would enter a model's window, and how
/// much was visibly cut.
class ContextPlan {
  final int budget;
  final int spent;
  final Set<String> selectedIds;
  final int excluded;

  const ContextPlan(
      {required this.budget,
      required this.spent,
      required this.selectedIds,
      required this.excluded});

  factory ContextPlan.fromJson(Map<String, dynamic> j) => ContextPlan(
        budget: j['budget'] is num ? (j['budget'] as num).toInt() : 0,
        spent: j['spent'] is num ? (j['spent'] as num).toInt() : 0,
        selectedIds: ((j['selected'] ?? []) as List)
            .whereType<Map<String, dynamic>>()
            .map((n) => '${n['id']}')
            .toSet(),
        excluded: j['excluded'] is num ? (j['excluded'] as num).toInt() : 0,
      );
}

class KnowledgeGraph {
  final List<GraphNode> nodes;
  final List<GraphEdge> edges;
  final ContextPlan? plan;

  const KnowledgeGraph(
      {required this.nodes, required this.edges, this.plan});

  factory KnowledgeGraph.fromJson(Map<String, dynamic> j) => KnowledgeGraph(
        nodes: ((j['nodes'] ?? []) as List)
            .whereType<Map<String, dynamic>>()
            .map(GraphNode.fromJson)
            .toList(),
        edges: ((j['edges'] ?? []) as List)
            .whereType<Map<String, dynamic>>()
            .map(GraphEdge.fromJson)
            .toList(),
        plan: j['context_plan'] is Map<String, dynamic>
            ? ContextPlan.fromJson(j['context_plan'] as Map<String, dynamic>)
            : null,
      );
}
