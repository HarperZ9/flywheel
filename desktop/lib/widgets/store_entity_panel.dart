// store_entity_panel.dart -- the content-addressed store, read and written.
//
// Reading is a plain query: kind, project, and the eid/sha of every row.
// Writing is not. A put appends to the audit chain on disk, so it goes
// through the grant sheet and the operator sees the kind being written
// before it lands. Data whose keys look like credentials is refused by the
// operation model rather than stored.

import 'dart:convert';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'operation_grant_sheet.dart';

class StoreEntityPanel extends StatefulWidget {
  final GatewayClient client;
  const StoreEntityPanel({super.key, required this.client});

  @override
  State<StoreEntityPanel> createState() => _StorePanelState();
}

class _StorePanelState extends State<StoreEntityPanel> {
  final _kind = TextEditingController();
  final _project = TextEditingController();
  final _data = TextEditingController(text: '{}');
  List<Map<String, dynamic>> _rows = const [];
  Map<String, dynamic>? _put;
  String? _error;
  bool _loaded = false;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _query();
  }

  @override
  void dispose() {
    _kind.dispose();
    _project.dispose();
    _data.dispose();
    super.dispose();
  }

  Future<void> _query() async {
    final kind = _kind.text.trim();
    final project = _project.text.trim();
    try {
      final r = await widget.client.postJson('/api/store/query', {
        if (kind.isNotEmpty) 'kind': kind,
        if (project.isNotEmpty) 'project': project,
        'limit': 50,
      });
      final rows = r['entities'];
      if (mounted) {
        setState(() {
          _rows = rows is List
              ? rows.whereType<Map>().map(Map<String, dynamic>.from).toList()
              : const [];
          _loaded = true;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _putEntity() async {
    final kind = _kind.text.trim();
    if (kind.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final decoded = jsonDecode(_data.text.trim().isEmpty
          ? '{}'
          : _data.text.trim());
      if (decoded is! Map<String, dynamic>) {
        throw const FormatException('data must be a JSON object');
      }
      final project = _project.text.trim();
      final requestId = 'store-${DateTime.now().microsecondsSinceEpoch}';
      final r = await authorizeGatewayOperation<Map<String, dynamic>>(
        context,
        GatewayOperation.exact(
          action: 'store.put',
          clientRequestId: requestId,
          operation: {
            'kind': kind,
            'data': decoded,
            if (project.isNotEmpty) 'project': project,
          },
        ),
        (body) => widget.client.postJson('/api/store/entity', body),
        currentOperation: () => null,
      );
      if (!mounted) return;
      setState(() => _put = r);
      await _query();
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
          const Kicker('entity store · content-addressed, chain-audited'),
          const SizedBox(height: FwLayout.s1),
          Text(
              'The same content under the same id re-derives the same hash. '
              'A put is a write to the audit chain, so it asks first.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            Expanded(
              child: TextField(
                controller: _kind,
                enabled: !_busy,
                onSubmitted: (_) => _query(),
                style: fwMono(t, size: 11.5, color: t.ink),
                decoration:
                    const InputDecoration(isDense: true, labelText: 'kind'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            Expanded(
              child: TextField(
                controller: _project,
                enabled: !_busy,
                onSubmitted: (_) => _query(),
                style: fwMono(t, size: 11.5, color: t.ink),
                decoration: const InputDecoration(
                    isDense: true,
                    labelText: 'project',
                    hintText: 'optional'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            OutlinedButton(
                onPressed: _busy ? null : _query, child: const Text('Query')),
          ]),
          const SizedBox(height: FwLayout.s2),
          TextField(
            controller: _data,
            enabled: !_busy,
            maxLines: 3,
            style: fwMono(t, size: 11.5, color: t.ink),
            decoration: const InputDecoration(
                isDense: true,
                labelText: 'data (JSON object)',
                hintText: 'keys that read as credentials are refused'),
          ),
          const SizedBox(height: FwLayout.s3),
          FilledButton(
            onPressed: _busy ? null : _putEntity,
            child: Text(_busy ? 'Storing…' : 'Store this entity'),
          ),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('The store did not answer: $_error'),
          ],
          if (_put != null) ...[
            const SizedBox(height: FwLayout.s3),
            HashText('stored', '${_put!['sha256'] ?? ''}', keep: 16),
            const SizedBox(height: 3),
            HashText('chain', '${_put!['chain_hash'] ?? ''}', keep: 16),
          ],
          const SizedBox(height: FwLayout.s4),
          _rowsBlock(t),
        ],
      ),
    );
  }

  Widget _rowsBlock(FwTokens t) {
    if (!_loaded) {
      return const HonestNull('The store has not been read yet.');
    }
    if (_rows.isEmpty) {
      return const HonestNull(
          'No entity matches. An empty store is a true answer about this '
          'run root, not a missing one.');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final row in _rows.take(50))
          Padding(
            padding: const EdgeInsets.only(bottom: 3),
            child: Row(children: [
              SizedBox(
                width: 140,
                child: Text('${row['kind'] ?? ''}',
                    overflow: TextOverflow.ellipsis,
                    style: fwMono(t, size: 11, color: t.ink)),
              ),
              Expanded(
                child: Text('${row['project'] ?? ''}',
                    overflow: TextOverflow.ellipsis,
                    style: fwMono(t, size: 11, color: t.inkFaint)),
              ),
              HashText('eid', '${row['sha256'] ?? ''}', keep: 12),
            ]),
          ),
      ],
    );
  }
}
