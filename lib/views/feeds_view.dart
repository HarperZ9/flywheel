// feeds_view.dart — fresh signal across every operator domain, fetched
// through the gather lane so each item carries provenance. A dead feed is
// a named error alongside the items that arrived; the roster ships in the
// payload so coverage is visible, never silently capped.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

const _domains = [
  'science',
  'programming',
  'art',
  'design',
  'marketing',
  'accountability',
];

class FeedsView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const FeedsView({super.key, required this.client, required this.alive});

  @override
  State<FeedsView> createState() => _FeedsViewState();
}

class _FeedsViewState extends State<FeedsView> {
  String _domain = 'science';
  bool _loading = false;
  List<Map<String, dynamic>> _items = [];
  Map<String, String> _errors = {};
  String? _error;
  bool _fetched = false;

  Future<void> _load() async {
    if (!widget.alive || _loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final doc = await widget.client.feeds(domain: _domain);
      if (mounted) {
        setState(() {
          _fetched = true;
          _items = ((doc['items'] ?? []) as List)
              .whereType<Map<String, dynamic>>()
              .toList();
          _errors = (doc['errors'] is Map<String, dynamic>)
              ? (doc['errors'] as Map<String, dynamic>)
                  .map((k, v) => MapEntry(k, '$v'))
              : {};
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. Feeds appear when it runs.',
          command: 'flywheel up');
    }
    final t = context.fw;
    return ViewScroll(
      children: [
        SectionHeader('Feeds',
            kicker: 'fresh signal, every domain, with provenance',
            trailing: FilledButton(
                onPressed: _loading ? null : _load,
                child: Text(_loading ? 'Fetching…' : 'Fetch'))),
        const SizedBox(height: FwLayout.s3),
        Text(
          'Live intake across the domains this platform serves, through the '
          'gather lane. A fetch is a request, not a heartbeat: nothing '
          'polls on its own.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: FwLayout.s3),
        Wrap(
          spacing: FwLayout.s2,
          runSpacing: FwLayout.s2,
          children: [
            for (final d in _domains)
              OutlinedButton(
                style: d == _domain
                    ? OutlinedButton.styleFrom(
                        side: BorderSide(color: t.drift))
                    : null,
                onPressed: () {
                  setState(() => _domain = d);
                  _load();
                },
                child: Text(d),
              ),
          ],
        ),
        const SizedBox(height: FwLayout.s4),
        if (_error != null) HonestNull('Failed: $_error'),
        for (final e in _errors.entries)
          Padding(
            padding: const EdgeInsets.only(bottom: FwLayout.s2),
            child: HonestNull('feed "${e.key}" failed: ${e.value}'),
          ),
        if (_fetched && _items.isEmpty && _errors.isEmpty && _error == null)
          const HonestNull('The fetch returned no items — an empty feed is '
              'a result, not a blank.'),
        if (_items.isNotEmpty)
          HairlineCard(
            child: Column(children: [
              for (final i in _items)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SizedBox(
                          width: 120,
                          child: Text('${i['feed']}',
                              style: fwMono(t, size: 10.5,
                                  color: t.inkFaint))),
                      const SizedBox(width: FwLayout.s3),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('${i['title']}',
                                style: TextStyle(
                                    fontSize: 12.5, color: t.inkSoft)),
                            if ('${i['url']}'.isNotEmpty)
                              SelectableText('${i['url']}',
                                  style: fwMono(t, size: 10.5,
                                      color: t.inkMuted)),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
            ]),
          ),
        if (!_fetched && _error == null)
          Text('Pick a domain and fetch.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
      ],
    );
  }
}
