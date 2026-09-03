// retrieval_panel.dart -- retrieval that cites where it read.
//
// BM25 over the workspace, answered with file, line, score, and the hash of
// the excerpt itself, so a quoted line can be re-derived from the file rather
// than trusted. The denominator travels with the answer: how many files were
// indexed and how many were skipped, because a top hit out of eleven files is
// a different claim than a top hit out of eleven thousand.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class RetrievalPanel extends StatefulWidget {
  final GatewayClient client;
  const RetrievalPanel({super.key, required this.client});

  @override
  State<RetrievalPanel> createState() => _RetrievalPanelState();
}

class _RetrievalPanelState extends State<RetrievalPanel> {
  final _query = TextEditingController();
  final _root = TextEditingController();
  Map<String, dynamic>? _result;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _query.dispose();
    _root.dispose();
    super.dispose();
  }

  Future<void> _search() async {
    final query = _query.text.trim();
    if (query.isEmpty || _busy) return;
    final root = _root.text.trim();
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final r = await widget.client.postJson(
          '/api/retrieve',
          {
            'query': query,
            'k': 8,
            if (root.isNotEmpty) 'root': root,
          },
          timeout: const Duration(seconds: 60));
      if (mounted) setState(() => _result = r);
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
          const Kicker('retrieve · every hit carries its excerpt hash'),
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            Expanded(
              child: TextField(
                controller: _query,
                enabled: !_busy,
                onSubmitted: (_) => _search(),
                style: fwMono(t, size: 11.5, color: t.ink),
                decoration: const InputDecoration(
                    isDense: true, labelText: 'query'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            SizedBox(
              width: 200,
              child: TextField(
                controller: _root,
                enabled: !_busy,
                style: fwMono(t, size: 11.5, color: t.ink),
                decoration: const InputDecoration(
                    isDense: true,
                    labelText: 'root',
                    hintText: 'blank = this workspace'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            FilledButton(
              onPressed: _busy ? null : _search,
              child: Text(_busy ? 'Indexing…' : 'Retrieve'),
            ),
          ]),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('The search did not run: $_error'),
          ],
          if (_result != null) ...[
            const SizedBox(height: FwLayout.s3),
            _resultBlock(t, _result!),
          ],
        ],
      ),
    );
  }

  Widget _resultBlock(FwTokens t, Map<String, dynamic> r) {
    final hits = r['hits'] is List ? (r['hits'] as List) : const [];
    final indexed = r['indexed_files'];
    final skipped = r['skipped'];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
            '${hits.length} hit(s) out of ${indexed ?? '—'} indexed file(s), '
            '${skipped ?? '—'} skipped',
            style: fwMono(t, size: 11, color: t.inkFaint)),
        const SizedBox(height: FwLayout.s2),
        if (hits.isEmpty)
          const HonestNull(
              'Nothing in the index matched. An empty result is an answer, '
              'not a failure.')
        else
          for (final hit in hits.whereType<Map>()) _hitRow(t, hit),
      ],
    );
  }

  Widget _hitRow(FwTokens t, Map hit) => Padding(
        padding: const EdgeInsets.only(bottom: FwLayout.s3),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Expanded(
                child: Text('${hit['path']}:${hit['line']}',
                    overflow: TextOverflow.ellipsis,
                    style: fwMono(t, size: 11.5, color: t.ink)),
              ),
              Text('${hit['score']}',
                  style: fwMono(t, size: 11, color: t.inkFaint)),
            ]),
            const SizedBox(height: 3),
            SelectableText('${hit['excerpt'] ?? ''}',
                maxLines: 4,
                style: fwMono(t, size: 11, color: t.inkSoft)),
            const SizedBox(height: 3),
            Row(children: [
              HashText('excerpt', '${hit['excerpt_sha256'] ?? ''}', keep: 16),
              if (hit['truncated'] == true) ...[
                const SizedBox(width: FwLayout.s2),
                Text('truncated',
                    style: fwMono(t, size: 10.5, color: t.inkFaint)),
              ],
            ]),
          ],
        ),
      );
}
