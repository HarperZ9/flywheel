// tool_spec.dart — one probed MCP/lane tool, with its full argument schema.
//
// The engine's probe returns `tool_specs`: each tool's {name, description,
// inputSchema}. This model carries that verbatim so the desktop can render a
// real argument form instead of a blind {} box. It also falls back to the
// bare `tools` name list an older engine returns, so a name still yields a
// callable chip (with an empty schema). Parsing degrades, never crashes.

class ToolSpec {
  final String name;
  final String description;

  /// The tool's JSON Schema `inputSchema` (an object schema), verbatim.
  final Map<String, dynamic> inputSchema;

  const ToolSpec({
    required this.name,
    this.description = '',
    this.inputSchema = const {},
  });

  factory ToolSpec.fromJson(Map<String, dynamic> j) => ToolSpec(
        name: '${j['name'] ?? ''}',
        description: '${j['description'] ?? ''}',
        inputSchema: (j['inputSchema'] is Map)
            ? Map<String, dynamic>.from(j['inputSchema'] as Map)
            : const {},
      );

  /// Parse a probe result into specs. Prefers `tool_specs` (full schema);
  /// falls back to `tools` (bare names, empty schema) so an older probe still
  /// yields callable chips. Junk entries are dropped, not fatal.
  static List<ToolSpec> listFromProbe(Map<String, dynamic> probe) {
    final specs = probe['tool_specs'];
    if (specs is List) {
      return specs
          .whereType<Map>()
          .map((m) => ToolSpec.fromJson(Map<String, dynamic>.from(m)))
          .where((s) => s.name.isNotEmpty)
          .toList();
    }
    final names = probe['tools'];
    if (names is List) {
      return names
          .map((n) => ToolSpec(name: '$n'))
          .where((s) => s.name.isNotEmpty)
          .toList();
    }
    return const [];
  }

  /// The declared property schemas, in schema order (empty when none). Each
  /// value is that property's own sub-schema (type, enum, default, …).
  List<MapEntry<String, Map<String, dynamic>>> get properties {
    final props = inputSchema['properties'];
    if (props is! Map) return const [];
    final out = <MapEntry<String, Map<String, dynamic>>>[];
    props.forEach((k, v) {
      out.add(MapEntry(
          '$k',
          v is Map
              ? Map<String, dynamic>.from(v)
              : const <String, dynamic>{}));
    });
    return out;
  }

  /// The names of required properties (empty when the schema declares none).
  Set<String> get requiredFields {
    final req = inputSchema['required'];
    if (req is! List) return const {};
    return req.map((e) => '$e').toSet();
  }

  /// True when the schema declares at least one argument to fill.
  bool get hasDeclaredArgs => properties.isNotEmpty;
}
