// lint_index_sheet.dart — the code lane's in-context quality loop: lint the
// open workspace and jump straight to each finding in the editor, or read
// the index engine's view of the same root. Both were engine capabilities
// the primary code surface could not reach.

import 'dart:convert';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

void showLintIndexSheet(BuildContext context, GatewayClient client,
    String root, void Function(String path, int line) onOpen,
    {required bool index}) {
  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: context.fw.ground,
    builder: (ctx) => SizedBox(
      height: MediaQuery.of(ctx).size.height * 0.6,
      child: Padding(
        padding: const EdgeInsets.all(FwLayout.s5),
        child: LintIndexSheet(
            client: client, root: root, onOpen: onOpen, index: index),
      ),
    ),
  );
}

/// The editor's one-line quality bar: the status text, the lint and index
/// entries, and the view-changes link when a run left diffs behind.
class EditorQualityBar extends StatelessWidget {
  final String? status;
  final int diffCount;
  final VoidCallback onLint;
  final VoidCallback onIndex;
  final VoidCallback onShowDiffs;
  const EditorQualityBar(
      {super.key,
      required this.status,
      required this.diffCount,
      required this.onLint,
      required this.onIndex,
      required this.onShowDiffs});

  Widget _link(FwTokens t, String label, VoidCallback onTap,
          {bool hot = false}) =>
      MouseRegion(
        cursor: SystemMouseCursors.click,
        child: GestureDetector(
          onTap: onTap,
          child: Text(label,
              style: fwMono(t, size: 10.5, color: hot ? t.drift : t.inkMuted)
                  .copyWith(decoration: TextDecoration.underline)),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Container(
      width: double.infinity,
      padding:
          const EdgeInsets.symmetric(horizontal: FwLayout.s4, vertical: 4),
      child: Row(children: [
        Expanded(
          child: Text(status ?? '',
              overflow: TextOverflow.ellipsis,
              style: fwMono(t, size: 10.5, color: t.inkFaint)),
        ),
        _link(t, 'lint', onLint),
        const SizedBox(width: FwLayout.s3),
        _link(t, 'index', onIndex),
        if (diffCount > 0) ...[
          const SizedBox(width: FwLayout.s3),
          _link(t,
              'view changes ($diffCount file${diffCount == 1 ? '' : 's'})',
              onShowDiffs,
              hot: true),
        ],
      ]),
    );
  }
}

class LintIndexSheet extends StatefulWidget {
  final GatewayClient client;
  final String root;
  final void Function(String path, int line) onOpen;
  final bool index; // false = lint findings, true = index map
  const LintIndexSheet(
      {super.key,
      required this.client,
      required this.root,
      required this.onOpen,
      required this.index});

  @override
  State<LintIndexSheet> createState() => _LintIndexSheetState();
}

class _LintIndexSheetState extends State<LintIndexSheet> {
  Map<String, dynamic>? _doc;
  String? _error;

  @override
  void initState() {
    super.initState();
    _run();
  }

  Future<void> _run() async {
    try {
      final doc = widget.index
          ? await widget.client.indexProject(widget.root, view: 'map')
          : await widget.client.lintProject(widget.root);
      if (mounted) setState(() => _doc = doc);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    if (_error != null) return HonestNull('Failed: $_error');
    final doc = _doc;
    if (doc == null) {
      return const Center(
          child: SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2)));
    }
    if (widget.index) {
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Kicker('index · map of ${widget.root}'),
        const SizedBox(height: FwLayout.s3),
        Expanded(
          child: SingleChildScrollView(
            child: Align(
              alignment: Alignment.centerLeft,
              child: SelectableText(
                  const JsonEncoder.withIndent('  ').convert(doc),
                  style: fwMono(t, size: 11).copyWith(height: 1.5)),
            ),
          ),
        ),
      ]);
    }
    final findings = ((doc['findings'] ?? []) as List)
        .whereType<Map<String, dynamic>>()
        .toList();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Kicker('lint · ${doc['n_findings'] ?? findings.length} finding'
            '${findings.length == 1 ? '' : 's'}'),
        const Spacer(),
        if ('${doc['root_hash'] ?? ''}'.isNotEmpty)
          HashText('run', '${doc['root_hash']}', keep: 24),
      ]),
      const SizedBox(height: FwLayout.s3),
      if (findings.isEmpty)
        const HonestNull('No findings. A clean result is a receipt, '
            'not an absence.')
      else
        Expanded(
          child: ListView.builder(
            itemCount: findings.length,
            itemBuilder: (ctx, i) {
              final f = findings[i];
              final line = f['line'] is num ? (f['line'] as num).toInt() : 1;
              return InkWell(
                onTap: () {
                  Navigator.of(ctx).pop();
                  widget.onOpen('${f['file']}', line);
                },
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(children: [
                    SizedBox(
                        width: 260,
                        child: Text('${f['file']}:$line',
                            overflow: TextOverflow.ellipsis,
                            style: fwMono(t, size: 11, color: t.drift))),
                    const SizedBox(width: FwLayout.s3),
                    Expanded(
                        child: Text('${f['rule'] ?? ''} ${f['message'] ?? ''}',
                            style: fwMono(t, size: 11, color: t.inkMuted))),
                  ]),
                ),
              );
            },
          ),
        ),
    ]);
  }
}
