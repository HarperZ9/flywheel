// memory_view.dart — the Memory view: the durable, content-addressed store.
// Notes and folded spans live in one index under the run root; recall is
// verbatim with the span hash as provenance. An empty store says so.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class MemoryView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const MemoryView({super.key, required this.client, required this.alive});

  @override
  State<MemoryView> createState() => _MemoryViewState();
}

class _MemoryViewState extends State<MemoryView> {
  final _query = TextEditingController();
  final _note = TextEditingController();
  Map<String, dynamic>? _stats;
  List<Map<String, dynamic>> _results = [];
  List<Map<String, dynamic>> _browse = [];
  bool _searched = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(MemoryView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  Future<void> _load() async {
    await _loadStats();
    await _loadBrowse();
  }

  Future<void> _loadBrowse() async {
    if (!widget.alive) return;
    try {
      final r = await widget.client.memoryList(limit: 30);
      if (mounted) {
        setState(() => _browse = ((r['spans'] ?? []) as List)
            .whereType<Map<String, dynamic>>()
            .toList());
      }
    } catch (_) {/* stats error already surfaced */}
  }

  @override
  void dispose() {
    _query.dispose();
    _note.dispose();
    super.dispose();
  }

  Future<void> _loadStats() async {
    if (!widget.alive) return;
    try {
      final s = await widget.client.memoryStats();
      if (mounted) {
        setState(() {
          _stats = s;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _recall() async {
    final q = _query.text.trim();
    if (q.isEmpty) return;
    try {
      final r = await widget.client.memoryRecall(q);
      if (mounted) {
        setState(() {
          _results = ((r['results'] ?? []) as List)
              .whereType<Map<String, dynamic>>()
              .toList();
          _searched = true;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _addNote() async {
    final text = _note.text.trim();
    if (text.isEmpty) return;
    try {
      await widget.client.memoryNote(text);
      _note.clear();
      _load();
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. Memory appears when it runs.',
          command: 'flywheel up');
    }
    final t = context.fw;
    final spans = _stats?['spans'] ?? 0;
    final terms = _stats?['terms'] ?? 0;
    return ViewScroll(
      children: [
        const SectionHeader('Memory', kicker: 'durable, content-addressed'),
        const SizedBox(height: FwLayout.s3),
        Text(
          'One store under the run root: compaction folds spans into it, '
          'notes land beside them, and recall returns the verbatim content '
          'with its hash. The hash IS the provenance.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: FwLayout.s4),
        Row(
          children: [
            Expanded(child: StatTile(label: 'spans', value: '$spans')),
            const SizedBox(width: FwLayout.s3),
            Expanded(child: StatTile(label: 'indexed terms', value: '$terms')),
            const SizedBox(width: FwLayout.s3),
            Expanded(
                child: StatTile(
                    label: 'persisted',
                    value: (_stats?['persisted'] ?? false) ? 'yes' : 'empty',
                    status: (_stats?['persisted'] ?? false)
                        ? 'verified'
                        : 'absent')),
          ],
        ),
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull('Memory request failed: $_error'),
        ],
        const SizedBox(height: FwLayout.s5),
        const Kicker('recall · verbatim, ranked by rare-term overlap',
            hot: true),
        const SizedBox(height: FwLayout.s3),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _query,
                style: const TextStyle(fontSize: 13.5),
                decoration:
                    const InputDecoration(hintText: 'What do you remember about…'),
                onSubmitted: (_) => _recall(),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            FilledButton(onPressed: _recall, child: const Text('Recall')),
          ],
        ),
        const SizedBox(height: FwLayout.s3),
        if (_searched && _results.isEmpty)
          const HonestNull(
              'Nothing matched. The store only returns what it actually '
              'holds; it never paraphrases or invents.')
        else
          for (final r in _results) _resultCard(t, r),
        const SizedBox(height: FwLayout.s5),
        Kicker('stored · ${_browse.length} span${_browse.length == 1 ? '' : 's'}, '
            'browse without a query'),
        const SizedBox(height: FwLayout.s3),
        if (_browse.isEmpty)
          const HonestNull(
              'Nothing stored yet. Notes you add and spans the loop folds '
              'appear here, verbatim, each bound to its content hash.')
        else
          for (final r in _browse) _resultCard(t, r),
        const SizedBox(height: FwLayout.s5),
        const Kicker('add a note'),
        const SizedBox(height: FwLayout.s3),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: TextField(
                controller: _note,
                maxLines: 3,
                minLines: 2,
                style: const TextStyle(fontSize: 13.5),
                decoration: const InputDecoration(
                    hintText: 'A durable fact worth keeping…'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            FilledButton(onPressed: _addNote, child: const Text('Keep')),
          ],
        ),
      ],
    );
  }

  Widget _resultCard(FwTokens t, Map<String, dynamic> r) {
    final messages = (r['messages'] ?? []) as List;
    final content = messages.isNotEmpty && messages.first is Map
        ? '${(messages.first as Map)['content'] ?? ''}'
        : '';
    return Padding(
      padding: const EdgeInsets.only(bottom: FwLayout.s3),
      child: HairlineCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SelectableText(content,
                style: TextStyle(fontSize: 13, color: t.inkSoft, height: 1.5)),
            const SizedBox(height: FwLayout.s2),
            Row(
              children: [
                HashText('span', '${r['span_hash'] ?? ''}', keep: 20),
                const Spacer(),
                if (r['score'] != null)
                  Text('score ${r['score']}',
                      style: fwMono(t, size: 10.5, color: t.inkFaint)),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
