const rowanMcpCatalogSchema = 'flywheel.agent-mcp-catalog/v1';
const rowanMcpDiscoveryRequestSchema =
    'flywheel.agent-mcp-discovery-request/v1';
const rowanMcpDiscoveryResponseSchema =
    'flywheel.agent-mcp-discovery-response/v1';

final _rowanMcpId = RegExp(r'^[a-z][a-z0-9_]{0,23}$');
final _rowanMcpCatalogRef = RegExp(r'^[a-z][A-Za-z0-9_.-]{0,63}$');
final _rowanMcpTool = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,127}$');

final class RowanMcpCatalog {
  final List<RowanMcpServer> servers;
  const RowanMcpCatalog._(this.servers);

  factory RowanMcpCatalog.fromJson(Map<String, dynamic> json) {
    if (json['schema'] != rowanMcpCatalogSchema) {
      throw const FormatException('Rowan MCP catalog schema mismatch');
    }
    final rawServers = json['servers'];
    if (rawServers is! List) {
      throw const FormatException('Rowan MCP catalog servers are invalid');
    }
    return RowanMcpCatalog._(
      List<RowanMcpServer>.unmodifiable(
        rawServers.map((raw) =>
            RowanMcpServer.fromJson(Map<String, Object?>.from(raw as Map))),
      ),
    );
  }

  List<RowanMcpOption> get options => List<RowanMcpOption>.unmodifiable([
        for (final server in servers)
          if (server.available)
            for (final tool in server.tools)
              RowanMcpOption(
                serverId: server.serverId,
                catalogRef: server.catalogRef,
                sourceToolName: tool.sourceToolName,
              ),
      ]);
}

final class RowanMcpServer {
  final String serverId, catalogRef, availabilityStatus;
  final List<RowanMcpTool> tools;
  const RowanMcpServer._(
    this.serverId,
    this.catalogRef,
    this.availabilityStatus,
    this.tools,
  );

  factory RowanMcpServer.fromJson(Map<String, Object?> json) {
    final serverId = _requiredString(json, 'server_id', _rowanMcpId);
    final catalogRef =
        _requiredString(json, 'catalog_ref', _rowanMcpCatalogRef);
    final availability = json['availability'];
    if (availability is! Map) {
      throw const FormatException('Rowan MCP availability is invalid');
    }
    final status = availability['status'];
    if (status is! String || status.isEmpty) {
      throw const FormatException('Rowan MCP availability status is invalid');
    }
    final rawTools = json['tools'];
    if (rawTools is! List) {
      throw const FormatException('Rowan MCP tool list is invalid');
    }
    return RowanMcpServer._(
      serverId,
      catalogRef,
      status,
      List<RowanMcpTool>.unmodifiable(rawTools.map((raw) =>
          RowanMcpTool.fromJson(Map<String, Object?>.from(raw as Map)))),
    );
  }

  bool get available => availabilityStatus == 'available';
}

final class RowanMcpTool {
  final String sourceToolName;
  const RowanMcpTool._(this.sourceToolName);

  factory RowanMcpTool.fromJson(Map<String, Object?> json) => RowanMcpTool._(
        _requiredString(json, 'source_tool_name', _rowanMcpTool),
      );
}

final class RowanMcpOption {
  final String serverId, catalogRef, sourceToolName;
  const RowanMcpOption({
    required this.serverId,
    required this.catalogRef,
    required this.sourceToolName,
  });

  String get key => '$serverId\x1f$sourceToolName';
  String get label => '$serverId / $sourceToolName';
}

final class RowanMcpDiscoveryResponse {
  final Map<String, Object?> mcpAdmission;
  final Map<String, Object?> receipt;
  const RowanMcpDiscoveryResponse._(this.mcpAdmission, this.receipt);

  factory RowanMcpDiscoveryResponse.fromJson(Map<String, dynamic> json) {
    if (json['schema'] != rowanMcpDiscoveryResponseSchema) {
      throw const FormatException(
          'Rowan MCP discovery response schema mismatch');
    }
    final admission = json['mcp_admission'];
    final receipt = json['receipt'];
    if (admission is! Map || receipt is! Map) {
      throw const FormatException('Rowan MCP discovery response is invalid');
    }
    return RowanMcpDiscoveryResponse._(
      _deepMapCopy(Map<String, Object?>.from(admission)),
      _deepMapCopy(Map<String, Object?>.from(receipt)),
    );
  }
}

String _requiredString(
  Map<String, Object?> json,
  String field,
  RegExp pattern,
) {
  final value = json[field];
  if (value is String && pattern.hasMatch(value)) return value;
  throw FormatException('Rowan MCP $field is invalid');
}

Map<String, Object?> _deepMapCopy(Map<String, Object?> value) {
  final copy = <String, Object?>{};
  for (final entry in value.entries) {
    copy[entry.key] = _deepValueCopy(entry.value);
  }
  return Map<String, Object?>.unmodifiable(copy);
}

Object? _deepValueCopy(Object? value) {
  if (value == null || value is String || value is num || value is bool) {
    return value;
  }
  if (value is List) {
    return List<Object?>.unmodifiable(value.map(_deepValueCopy));
  }
  if (value is Map) return _deepMapCopy(Map<String, Object?>.from(value));
  throw const FormatException('Rowan MCP JSON value is invalid');
}
