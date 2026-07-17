// teachback_card.dart — the comprehension ledger's write: paste a diff,
// explain it in your own words, get graded mechanically. Passing means the
// explanation names the changed files, covers the key changed identifiers,
// and is not the diff pasted back. The receipt is stored either way; an
// honest fail is still evidence.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class TeachbackCard extends StatefulWidget {
  final GatewayClient client;
  final VoidCallback? onStored;
  const TeachbackCard({super.key, required this.client, this.onStored});

  @override
  State<TeachbackCard> createState() => _TeachbackCardState();
}

class _TeachbackCardState extends State<TeachbackCard> {
  final _diff = TextEditingController();
  final _explanation = TextEditingController();
  bool _grading = false;
  Map<String, dynamic>? _receipt;
  String? _error;

  @override
  void dispose() {
    _diff.dispose();
    _explanation.dispose();
    super.dispose();
  }

  Future<void> _grade() async {
    if (_grading ||
        _diff.text.trim().isEmpty ||
        _explanation.text.trim().isEmpty) {
      return;
    }
    setState(() {
      _grading = true;
      _error = null;
      _receipt = null;
    });
    try {
      final doc =
          await widget.client.explain(_diff.text, _explanation.text);
      if (mounted) setState(() => _receipt = doc);
      widget.onStored?.call();
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _grading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final r = _receipt;
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        TextField(
          controller: _diff,
          maxLines: 5,
          minLines: 2,
          style: fwMono(t, size: 11.5),
          decoration:
              const InputDecoration(hintText: 'The diff you are explaining…'),
        ),
        const SizedBox(height: FwLayout.s2),
        TextField(
          controller: _explanation,
          maxLines: 4,
          minLines: 2,
          style: const TextStyle(fontSize: 12.5),
          decoration: const InputDecoration(
              hintText: 'Explain the change in your own words…'),
        ),
        const SizedBox(height: FwLayout.s3),
        Row(children: [
          FilledButton(
            onPressed: _grading ? null : _grade,
            child: Text(_grading ? 'Grading…' : 'Grade the teach-back'),
          ),
          const SizedBox(width: FwLayout.s3),
          Flexible(
            child: Text('graded mechanically; pasting the diff back cannot pass',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: fwMono(t, size: 10, color: t.inkFaint)),
          ),
        ]),
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s2),
          HonestNull('Grading failed: $_error'),
        ],
        if (r != null) ...[
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            VerdictPill(r['passed'] == true ? 'held' : 'not yet held',
                status: r['passed'] == true ? 'verified' : 'drift'),
            const SizedBox(width: FwLayout.s2),
            if (r['coverage'] is num)
              Text(
                  'coverage ${((r['coverage'] as num) * 100).round()}%'
                  '${r['own_words_share'] is num ? ' · own words ${((r['own_words_share'] as num) * 100).round()}%' : ''}',
                  style: fwMono(t, size: 11, color: t.inkMuted)),
          ]),
          if ('${r['stored'] ?? ''}'.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s2),
            HashText('stored', '${r['stored']}', keep: 32),
          ],
        ],
      ]),
    );
  }
}
