// discourse_view.dart — the Discourse destination.
//
// Point it at a gathered comment corpus and it renders chorus's own digest:
// the themes people are voicing, ranked by engagement and sentiment, each with
// its distribution and its surfaced dissent, under a re-checkable receipt.
// Canon: color is a verdict only, so sentiment shares render in neutral ink;
// the single verdict mark is the receipt's verify status.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/discourse.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/discourse_recent.dart';
import '../widgets/fw.dart';

class DiscourseView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const DiscourseView({super.key, required this.client, required this.alive});

  @override
  State<DiscourseView> createState() => _DiscourseViewState();
}

class _DiscourseViewState extends State<DiscourseView> {
  final _corpus = TextEditingController();
  final _root = TextEditingController();
  bool _loading = false;
  bool _scanning = false;
  String? _error;
  DiscourseDigest? _digest;
  List<CorpusRef> _corpora = const [];

  @override
  void dispose() {
    _corpus.dispose();
    _root.dispose();
    super.dispose();
  }

  Future<void> _scan() async {
    final root = _root.text.trim();
    if (root.isEmpty) {
      setState(() => _error = 'Name a root directory to scan for gather corpora.');
      return;
    }
    setState(() {
      _scanning = true;
      _error = null;
    });
    try {
      final env = await widget.client.discourseCorpora(root);
      if (env['error'] != null) {
        setState(() => _corpora = const []);
        setState(() => _error = env['error'].toString());
      } else {
        setState(() => _corpora = CorpusRef.listFrom(env));
      }
    } catch (e) {
      setState(() => _error = 'scan failed: $e');
    } finally {
      if (mounted) setState(() => _scanning = false);
    }
  }

  void _pick(CorpusRef c) {
    _corpus.text = c.path;
    _synthesize();
  }

  Future<void> _synthesize() async {
    final path = _corpus.text.trim();
    if (path.isEmpty) {
      setState(() => _error = 'Name a corpus: a gather corpus directory or a JSON row list.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final env = await widget.client.discourse(path);
      if (env['error'] != null) {
        setState(() => _error = env['error'].toString());
      } else {
        setState(() => _digest = DiscourseDigest.fromEnvelope(env));
      }
    } catch (e) {
      setState(() => _error = 'request failed: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty('The engine is offline.', command: 'flywheel app --port 8799');
    }
    final d = _digest;
    return ViewScroll(children: [
      SectionHeader('Discourse',
          kicker: 'PERCEPTION',
          trailing: FilledButton(
            onPressed: _loading ? null : _synthesize,
            child: Text(_loading ? 'Synthesizing…' : 'Synthesize'),
          )),
      const SizedBox(height: FwLayout.s3),
      TextField(
        controller: _corpus,
        onSubmitted: (_) => _synthesize(),
        decoration: const InputDecoration(
          labelText: 'Corpus',
          hintText: 'a gather corpus directory, or a JSON list of rows',
        ),
      ),
      const SizedBox(height: FwLayout.s3),
      _corpusPicker(context),
      const SizedBox(height: FwLayout.s5),
      SectionHeader('Scheduled', kicker: 'DAEMON DIGESTS'),
      const SizedBox(height: FwLayout.s3),
      DiscourseRecent(client: widget.client),
      if (_error != null) ...[
        const SizedBox(height: FwLayout.s4),
        HonestNull(_error!),
      ],
      if (d != null) ...[
        const SizedBox(height: FwLayout.s5),
        _summary(context, d),
        const SizedBox(height: FwLayout.s5),
        SectionHeader('Themes', kicker: 'RANKED BY WEIGHT'),
        const SizedBox(height: FwLayout.s3),
        if (d.themes.isEmpty)
          const HonestNull('No themes: the corpus held no discourse items.')
        else
          for (final t in d.themes.take(24)) ...[
            _themeCard(context, t),
            const SizedBox(height: FwLayout.s3),
          ],
      ],
    ]);
  }

  Widget _corpusPicker(BuildContext context) {
    final fw = context.fw;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(children: [
          Expanded(
            child: TextField(
              controller: _root,
              onSubmitted: (_) => _scan(),
              decoration: const InputDecoration(
                labelText: 'Or scan a root for gathered runs',
                hintText: 'a directory that holds gather corpora',
                isDense: true,
              ),
            ),
          ),
          const SizedBox(width: FwLayout.s3),
          OutlinedButton(
            onPressed: _scanning ? null : _scan,
            child: Text(_scanning ? 'Scanning…' : 'Scan'),
          ),
        ]),
        if (_corpora.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s3),
          Wrap(
            spacing: FwLayout.s2,
            runSpacing: FwLayout.s2,
            children: [
              for (final c in _corpora)
                InkWell(
                  onTap: () => _pick(c),
                  borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
                  child: HairlineCard(
                    padding: const EdgeInsets.symmetric(
                        horizontal: FwLayout.s3, vertical: FwLayout.s2),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(c.subject.isEmpty ? c.name : c.subject,
                            style: Theme.of(context).textTheme.bodyMedium,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis),
                        const SizedBox(height: 2),
                        Text('${c.name}  ·  ${c.comments} comments',
                            style: fwMono(fw, size: 11, color: fw.inkFaint)),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        ],
      ],
    );
  }

  Widget _summary(BuildContext context, DiscourseDigest d) {
    final verdict = d.verified ? 'verified' : 'drift';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        AdaptiveTiles(children: [
          StatTile(label: 'Comments', value: '${d.nItems}'),
          StatTile(label: 'Themes', value: '${d.themes.length}'),
          StatTile(
              label: 'Engagement',
              value: '${d.engagementPresent}/${d.engagementTotal}'),
          StatTile(
              label: 'Receipt',
              value: d.verified ? 'verified' : 'drift',
              status: verdict),
        ]),
        const SizedBox(height: FwLayout.s3),
        Row(children: [
          VerdictPill('receipt $verdict', status: verdict),
          const SizedBox(width: FwLayout.s3),
          if (d.digestSha.isNotEmpty)
            Flexible(child: HashText('digest', d.digestSha)),
        ]),
        if (!d.engagementComplete) ...[
          const SizedBox(height: FwLayout.s3),
          const HonestNull(
              'Not every item carried an engagement signal, so the ranking is '
              'sentiment-weighted only for those. A missing like count is an '
              'honest null, never counted as zero.'),
        ],
        if (d.coarseness.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull(d.coarseness),
        ],
      ],
    );
  }

  Widget _themeCard(BuildContext context, DiscourseTheme t) {
    final fw = context.fw;
    String pct(double v) => '${(v * 100).round()}%';
    final mean = t.meanCompound >= 0
        ? '+${t.meanCompound.toStringAsFixed(2)}'
        : t.meanCompound.toStringAsFixed(2);
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(
              child: Text(t.label,
                  style: Theme.of(context).textTheme.titleMedium,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis),
            ),
            const SizedBox(width: FwLayout.s2),
            Text('${t.size}  ·  w ${t.weightedScore.toStringAsFixed(1)}',
                style: fwMono(fw, size: 12, color: fw.inkFaint)),
          ]),
          const SizedBox(height: FwLayout.s2),
          // Sentiment is a WEIGHT, not a verdict: neutral ink only, never the
          // verified/drift palette.
          Text(
            'positive ${pct(t.posShare)}   ·   neutral ${pct(t.neuShare)}   ·   '
            'negative ${pct(t.negShare)}   ·   mean $mean',
            style: fwMono(fw, size: 12, color: fw.inkSoft),
          ),
          if (t.dissent != null) ...[
            const SizedBox(height: FwLayout.s2),
            Text('dissent: ${t.dissent}',
                style: fwMono(fw, size: 11.5, color: fw.inkMuted)),
          ],
        ],
      ),
    );
  }
}
