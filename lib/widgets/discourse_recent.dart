// discourse_recent.dart — the daemon's scheduled digests, read-only.
//
// Points at a chorus daemon store and lists what it has synthesized on a
// schedule, newest first. Each row shows the subject, the comment and theme
// counts, and the receipt verdict (the one colored mark; everything else is
// ink). Nothing is re-run here — this is the daemon's own answer.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/discourse.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class DiscourseRecent extends StatefulWidget {
  final GatewayClient client;
  const DiscourseRecent({super.key, required this.client});

  @override
  State<DiscourseRecent> createState() => _DiscourseRecentState();
}

class _DiscourseRecentState extends State<DiscourseRecent> {
  final _store = TextEditingController(text: '.chorus-run');
  bool _loading = false;
  String? _error;
  List<DigestRef> _digests = const [];
  bool _loaded = false;

  @override
  void dispose() {
    _store.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    final store = _store.text.trim();
    if (store.isEmpty) {
      setState(() => _error = 'Name the daemon store directory.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final env = await widget.client.discourseDigests(store);
      if (env['error'] != null) {
        setState(() {
          _digests = const [];
          _error = env['error'].toString();
        });
      } else {
        setState(() => _digests = DigestRef.listFrom(env));
      }
    } catch (e) {
      setState(() => _error = 'request failed: $e');
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
          _loaded = true;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final fw = context.fw;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(children: [
          Expanded(
            child: TextField(
              controller: _store,
              onSubmitted: (_) => _refresh(),
              decoration: const InputDecoration(
                labelText: 'Daemon store',
                hintText: 'where the chorus daemon writes digests',
                isDense: true,
              ),
            ),
          ),
          const SizedBox(width: FwLayout.s3),
          OutlinedButton(
            onPressed: _loading ? null : _refresh,
            child: Text(_loading ? 'Loading…' : 'Refresh'),
          ),
        ]),
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull(_error!),
        ],
        if (_loaded && _error == null && _digests.isEmpty) ...[
          const SizedBox(height: FwLayout.s3),
          const HonestNull(
              'No digests yet. Run: chorus daemon --watchlist watchlist.json '
              '--store .chorus-run'),
        ],
        for (final g in _digests) ...[
          const SizedBox(height: FwLayout.s2),
          HairlineCard(
            padding: const EdgeInsets.symmetric(
                horizontal: FwLayout.s4, vertical: FwLayout.s3),
            child: Row(children: [
              Expanded(
                child: Text(
                  g.respondsTo.isEmpty ? '(untitled corpus)' : g.respondsTo,
                  style: fwMono(fw, size: 12.5),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: FwLayout.s3),
              Text('${g.nItems} · ${g.themes} themes',
                  style: fwMono(fw, size: 11.5, color: fw.inkFaint)),
              const SizedBox(width: FwLayout.s3),
              VerdictDot(g.verified ? 'verified' : 'drift'),
            ]),
          ),
        ],
      ],
    );
  }
}
