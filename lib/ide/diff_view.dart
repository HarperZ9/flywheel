// diff_view.dart — renders file diffs in the INK ramp, never the verdict
// palette. A diff is raw, unaccepted, unreviewed text; painting an added line
// in verified-green would assert a verdict the engine never made. Added lines
// are present (ink), removed lines recede (faint ink), distinguished by the
// +/- glyph and a neutral ground tint. Color stays a verdict only.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import 'diff.dart';

/// The style for one diff line: a glyph, an ink-ramp color, and a neutral
/// ground tint. Pure and verdict-free so a stranger (and a test) can confirm
/// no verdict color leaks into raw code.
class DiffLineStyle {
  final String marker;
  final Color color;
  final Color background;
  const DiffLineStyle(this.marker, this.color, this.background);
}

DiffLineStyle diffLineStyle(FwTokens t, DiffKind kind) => switch (kind) {
      // added: the substance, full ink, on a faint neutral wash
      DiffKind.add => DiffLineStyle('+', t.ink, t.ink.withValues(alpha: 0.04)),
      // removed: receding, faint ink, no ground
      DiffKind.del => DiffLineStyle('−', t.inkFaint, Colors.transparent),
      DiffKind.same => DiffLineStyle(' ', t.inkFaint, Colors.transparent),
    };

/// The +/- count color: ink ramp, never a verdict. Added reads present
/// (inkMuted), removed reads receding (inkFaint); the glyph carries the sign.
Color diffCountColor(FwTokens t, {required bool added}) =>
    added ? t.inkMuted : t.inkFaint;

/// The bottom-sheet wrapper the code lane opens after a run: the diff panel
/// at 70% height with the change-request callback threaded through.
void showDiffSheet(BuildContext context, List<FileDiff> diffs,
    void Function(FileDiff diff, String anchor, String note) onRequest) {
  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: context.fw.ground,
    builder: (ctx) => SizedBox(
      height: MediaQuery.of(ctx).size.height * 0.7,
      child: DiffViewPanel(diffs: diffs, onRequest: onRequest),
    ),
  );
}

class DiffViewPanel extends StatelessWidget {
  final List<FileDiff> diffs;

  /// Landscape import 10: a change request anchored to the exact change it
  /// was written against (path + anchor over the changed lines).
  final void Function(FileDiff diff, String anchor, String note)? onRequest;
  const DiffViewPanel({super.key, required this.diffs, this.onRequest});

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
                      style: fwMono(t,
                          size: 11, color: diffCountColor(t, added: true))),
                  const SizedBox(width: 6),
                  Text('−${d.removed}',
                      style: fwMono(t,
                          size: 11, color: diffCountColor(t, added: false))),
                  if (onRequest != null)
                    Builder(builder: (context) {
                      return IconButton(
                        icon: const Icon(Icons.rate_review_outlined,
                            size: 15),
                        tooltip: 'request change on this diff',
                        visualDensity: VisualDensity.compact,
                        onPressed: () => _requestDialog(context, d),
                      );
                    }),
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

  Future<void> _requestDialog(BuildContext context, FileDiff d) async {
    final note = TextEditingController();
    final anchor = changeAnchor(d);
    final submitted = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: ctx.fw.ground,
        title: Text('Request change · ${d.path}',
            style: Theme.of(ctx).textTheme.titleMedium),
        content: SizedBox(
          width: 420,
          child: TextField(
            controller: note,
            autofocus: true,
            maxLines: 3,
            minLines: 1,
            style: const TextStyle(fontSize: 12.5),
            decoration: InputDecoration(
                hintText: 'What should change here…',
                helperText: 'anchored to $anchor',
                helperStyle: fwMono(ctx.fw, size: 10.5)),
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: const Text('Add request')),
        ],
      ),
    );
    if (submitted == true && note.text.trim().isNotEmpty) {
      onRequest!(d, anchor, note.text.trim());
    }
    note.dispose();
  }

  Widget _line(FwTokens t, DiffLine l) {
    final s = diffLineStyle(t, l.kind);
    return Container(
      color: s.background,
      padding: const EdgeInsets.symmetric(horizontal: FwLayout.s3),
      child: Text('${s.marker} ${l.text}',
          style: fwMono(t, size: 11.5, color: s.color)),
    );
  }
}
