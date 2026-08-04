// model_selector.dart — the per-endpoint model switch. The endpoint picker
// chooses WHO answers; this chooses WHICH model that endpoint serves. The
// roster comes from GET /api/models via a caller-supplied loader (never a
// client), the default entry is labeled, and an unreachable lister degrades
// to an honest reason without ever blocking a send.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class ModelSelectorButton extends StatelessWidget {
  /// Loads the /api/models doc for the current endpoint when the picker opens.
  final Future<Map<String, dynamic>> Function() loadModels;

  /// The chosen model id; null or empty means the endpoint default.
  final String? current;

  /// Fires with the picked id; '' means "use the endpoint default".
  final ValueChanged<String> onSelect;
  final bool enabled;

  const ModelSelectorButton({
    super.key,
    required this.loadModels,
    required this.current,
    required this.onSelect,
    this.enabled = true,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final label =
        (current == null || current!.isEmpty) ? 'default model' : current!;
    return OutlinedButton(
      onPressed: !enabled
          ? null
          : () async {
              final picked = await showDialog<String>(
                context: context,
                builder: (_) => _ModelRosterDialog(
                    loadModels: loadModels, current: current),
              );
              if (picked != null) onSelect(picked);
            },
      style: OutlinedButton.styleFrom(
        padding:
            const EdgeInsets.symmetric(horizontal: FwLayout.s3, vertical: 8),
        side: BorderSide(color: t.line),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(Icons.memory_outlined, size: 13, color: t.inkFaint),
        const SizedBox(width: FwLayout.s2),
        Text(label, style: fwMono(t, size: 12.5, color: t.inkSoft)),
        const SizedBox(width: 4),
        Icon(Icons.expand_more_rounded, size: 15, color: t.inkFaint),
      ]),
    );
  }
}

class _ModelRosterDialog extends StatefulWidget {
  final Future<Map<String, dynamic>> Function() loadModels;
  final String? current;
  const _ModelRosterDialog({required this.loadModels, required this.current});

  @override
  State<_ModelRosterDialog> createState() => _ModelRosterDialogState();
}

class _ModelRosterDialogState extends State<_ModelRosterDialog> {
  Map<String, dynamic>? _doc;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    Map<String, dynamic> doc;
    try {
      doc = await widget.loadModels();
    } catch (e) {
      // the engine is offline or the route failed: the default stays
      // selectable and the reason is shown, never a dead dialog
      doc = {'models': [], 'reason': 'model listing unavailable: $e'};
    }
    if (mounted) setState(() => _doc = doc);
  }

  List<(String, bool)> get _rows {
    final raw = _doc?['models'];
    final rows = <(String, bool)>[];
    if (raw is List) {
      for (final m in raw) {
        if (m is! Map) continue;
        final id = '${m['id'] ?? ''}';
        if (id.isNotEmpty) rows.add((id, '${m['default']}' == 'true'));
      }
    }
    // no roster at all: the endpoint default stays a live choice
    if (rows.isEmpty) rows.add(('', true));
    return rows;
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final doc = _doc;
    final reason = '${doc?['reason'] ?? ''}';
    return Dialog(
      backgroundColor: t.ground,
      shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(FwLayout.radius),
          side: BorderSide(color: t.line)),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 380, maxHeight: 420),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(
                FwLayout.s4, FwLayout.s4, FwLayout.s4, FwLayout.s2),
            child: Row(children: [
              const Kicker('model'),
              const Spacer(),
              if (doc != null)
                Text('${doc['endpoint'] ?? ''}',
                    style: fwMono(t, size: 10.5, color: t.inkFaint)),
            ]),
          ),
          Divider(height: 1, color: t.hairline),
          if (doc == null)
            Padding(
              padding: const EdgeInsets.all(FwLayout.s4),
              child: Text('loading models…',
                  style: fwMono(t, size: 11.5, color: t.inkFaint)),
            )
          else ...[
            if (reason.isNotEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(
                    FwLayout.s4, FwLayout.s3, FwLayout.s4, FwLayout.s1),
                child: HonestNull(reason),
              ),
            Flexible(
              child: ListView(
                shrinkWrap: true,
                padding: const EdgeInsets.symmetric(vertical: FwLayout.s2),
                children: [
                  for (final (id, isDefault) in _rows)
                    _row(t, id, isDefault),
                ],
              ),
            ),
          ],
        ]),
      ),
    );
  }

  Widget _row(FwTokens t, String id, bool isDefault) {
    final cur = widget.current ?? '';
    final selected = cur.isEmpty ? isDefault : cur == id;
    return InkWell(
      // the default row pops '' — "no override" — so a send with the
      // default carries no model field at all
      onTap: () => Navigator.of(context).pop(isDefault ? '' : id),
      child: Container(
        padding: const EdgeInsets.symmetric(
            horizontal: FwLayout.s4, vertical: FwLayout.s3),
        color: selected ? t.panel : null,
        child: Row(children: [
          Icon(selected ? Icons.check_rounded : Icons.memory_outlined,
              size: 15, color: selected ? t.ink : t.inkFaint),
          const SizedBox(width: FwLayout.s3),
          Expanded(
            child: Text(id.isEmpty ? 'endpoint default' : id,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: fwMono(t,
                    size: 12.5, color: selected ? t.ink : t.inkSoft)),
          ),
          if (isDefault)
            Text('default', style: fwMono(t, size: 10.5, color: t.inkFaint)),
        ]),
      ),
    );
  }
}
