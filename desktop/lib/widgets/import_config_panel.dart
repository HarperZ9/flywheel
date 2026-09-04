// import_config_panel.dart -- arrive with the setup you already have.
//
// Scans a workspace root for another harness's config and maps what it finds
// into one Flywheel profile. The panel gives the drops equal weight with the
// mappings: a rule that has no native equivalent is carried nowhere and named,
// rather than half-translated into something that would silently misbehave.
// Reading a foreign root and writing a profile is a write operation, so it
// goes through the grant sheet.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'operation_grant_sheet.dart';

class ImportConfigPanel extends StatefulWidget {
  final GatewayClient client;
  const ImportConfigPanel({super.key, required this.client});

  @override
  State<ImportConfigPanel> createState() => _ImportConfigPanelState();
}

class _ImportConfigPanelState extends State<ImportConfigPanel> {
  final _root = TextEditingController();
  Map<String, dynamic>? _manifest;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _root.dispose();
    super.dispose();
  }

  Future<void> _import() async {
    final root = _root.text.trim();
    if (root.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final requestId = 'import-${DateTime.now().microsecondsSinceEpoch}';
      final r = await authorizeGatewayOperation<Map<String, dynamic>>(
        context,
        GatewayOperation.exact(
          action: 'import.config',
          clientRequestId: requestId,
          operation: {'root': root},
        ),
        (body) => widget.client.postJson('/api/import', body,
            timeout: const Duration(seconds: 60)),
        currentOperation: () => null,
      );
      if (mounted) setState(() => _manifest = r);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('import another harness'),
          const SizedBox(height: FwLayout.s1),
          Text(
              'Instruction files, Cursor rules, and MCP servers are read from '
              'the root you name and mapped into one profile. Every source is '
              'hashed and every drop is reasoned, so what did not survive the '
              'move is as visible as what did.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            Expanded(
              child: TextField(
                controller: _root,
                enabled: !_busy,
                style: fwMono(t, size: 11.5, color: t.ink),
                decoration: const InputDecoration(
                    isDense: true,
                    labelText: 'workspace root',
                    hintText: 'the folder holding .claude, .cursor, AGENTS.md'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            FilledButton(
              onPressed: _busy ? null : _import,
              child: Text(_busy ? 'Reading…' : 'Import'),
            ),
          ]),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('Nothing was imported: $_error'),
          ],
          if (_manifest != null) ...[
            const SizedBox(height: FwLayout.s3),
            _manifestBlock(t, _manifest!),
          ],
        ],
      ),
    );
  }

  Widget _manifestBlock(FwTokens t, Map<String, dynamic> m) {
    final mappings = m['mappings'] is List ? (m['mappings'] as List) : const [];
    final dropped = m['dropped'] is List ? (m['dropped'] as List) : const [];
    final profile = m['profile'] is Map ? (m['profile'] as Map) : const {};
    final servers =
        profile['mcp_servers'] is Map ? (profile['mcp_servers'] as Map) : null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('${m['root'] ?? ''}', style: fwMono(t, size: 11, color: t.inkFaint)),
        const SizedBox(height: FwLayout.s2),
        if (mappings.isEmpty && dropped.isEmpty)
          const HonestNull(
              'No recognized harness config was found under that root. An '
              'empty import is an answer: nothing was invented to fill it.')
        else ...[
          Text('${mappings.length} mapped  ·  ${dropped.length} dropped  ·  '
              '${servers?.length ?? 0} MCP server(s)',
              style: fwMono(t, size: 11.5, color: t.ink)),
          for (final row in mappings.whereType<Map>()) _mappingRow(t, row),
          for (final row in dropped.whereType<Map>()) _droppedRow(t, row),
        ],
        if (m['stored'] != null) ...[
          const SizedBox(height: FwLayout.s2),
          HashText('stored', '${m['stored']}', keep: 16),
        ],
        if (m['note'] != null) ...[
          const SizedBox(height: FwLayout.s2),
          Text('${m['note']}',
              style: fwMono(t, size: 10.5, color: t.inkFaint)),
        ],
      ],
    );
  }

  Widget _mappingRow(FwTokens t, Map row) {
    final status = '${row['status'] ?? 'mapped'}';
    // partial and empty are not successes: a partial mapping left something
    // behind, and an empty one extracted nothing at all.
    final verdict = status == 'mapped'
        ? 'verified'
        : status == 'partial'
            ? 'drift'
            : 'unverifiable';
    return Padding(
      padding: const EdgeInsets.only(top: FwLayout.s2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            VerdictPill(status, status: verdict),
            const SizedBox(width: FwLayout.s2),
            Expanded(
              child: Text('${row['source'] ?? ''} → ${row['mapped_to'] ?? ''}',
                  overflow: TextOverflow.ellipsis,
                  style: fwMono(t, size: 11, color: t.inkSoft)),
            ),
          ]),
          if (row['sha256'] != null)
            Padding(
              padding: const EdgeInsets.only(top: 3),
              child: HashText('source', '${row['sha256']}', keep: 12),
            ),
        ],
      ),
    );
  }

  Widget _droppedRow(FwTokens t, Map row) => Padding(
        padding: const EdgeInsets.only(top: FwLayout.s2),
        child: HonestNull('${row['source'] ?? 'a source'}: '
            '${row['reason'] ?? 'carried nowhere'}'),
      );
}
