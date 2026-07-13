// diff_view.dart — renders file diffs in the verdict language: added lines
// carry the verified tint, removed lines the drift tint, context recedes.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import 'diff.dart';

class DiffViewPanel extends StatelessWidget {
  final List<FileDiff> diffs;
  const DiffViewPanel({super.key, required this.diffs});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return ListView(
      padding: const EdgeInsets.all(FwLayout.s4),
      children: [
        Row(
          children: [
            const Kicker('changes · open files', hot: true),
            const Spacer(),
            Text(
                '${diffs.fold(0, (s, d) => s + d.added)} added · '
                '${diffs.fold(0, (s, d) => s + d.removed)} removed',
                style: fwMono(t, size: 11, color: t.inkMuted)),
          ],
        ),
        const SizedBox(height: FwLayout.s3),
        for (final d in diffs) _fileDiff(t, d),
      ],
    );
  }

  Widget _fileDiff(FwTokens t, FileDiff d) {
    return Padding(
      padding: const EdgeInsets.only(bottom: FwLayout.s3),
      child: HairlineCard(
        padding: EdgeInsets.zero,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.symmetric(
                  horizontal: FwLayout.s3, vertical: FwLayout.s2),
              decoration: BoxDecoration(
                color: t.ground2,
                border: Border(bottom: BorderSide(color: t.hairline)),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(d.path,
                        overflow: TextOverflow.ellipsis,
                        style:
                            fwMono(t, size: 11.5, weight: FontWeight.w600)),
                  ),
                  Text('+${d.added}',
                      style: fwMono(t, size: 11, color: t.verified)),
                  const SizedBox(width: 6),
                  Text('−${d.removed}',
                      style: fwMono(t, size: 11, color: t.drift)),
                ],
              ),
            ),
            if (d.note != null)
              Padding(
                padding: const EdgeInsets.all(FwLayout.s3),
                child: HonestNull(d.note!),
              )
            else
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [for (final l in d.lines) _line(t, l)],
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _line(FwTokens t, DiffLine l) {
    final (marker, color, bg) = switch (l.kind) {
      DiffKind.add => ('+', t.verified, t.verified.withValues(alpha: 0.08)),
      DiffKind.del => ('−', t.drift, t.drift.withValues(alpha: 0.08)),
      DiffKind.same => (' ', t.inkFaint, Colors.transparent),
    };
    return Container(
      color: bg,
      padding: const EdgeInsets.symmetric(horizontal: FwLayout.s3),
      child: Text('$marker ${l.text}',
          style: fwMono(t,
              size: 11.5,
              color: l.kind == DiffKind.same ? t.inkFaint : t.inkSoft)),
    );
  }
}
