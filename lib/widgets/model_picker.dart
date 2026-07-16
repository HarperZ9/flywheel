// model_picker.dart — a searchable, credential-aware model picker. A bare
// dropdown makes you scroll a flat list; this opens a small panel you can type
// into, with each endpoint's key/credential state shown at a glance, so choosing
// the model you want stays fast even with a long roster.

import 'package:flutter/material.dart';

import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';

/// The button that shows the current model and opens the picker.
class ModelPickerButton extends StatelessWidget {
  final List<EndpointRow> endpoints;
  final String? current;
  final ValueChanged<String> onSelect;
  final bool enabled;
  const ModelPickerButton({
    super.key,
    required this.endpoints,
    required this.current,
    required this.onSelect,
    this.enabled = true,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return OutlinedButton(
      onPressed: (!enabled || endpoints.isEmpty)
          ? null
          : () async {
              final picked =
                  await showModelPicker(context, endpoints, current);
              if (picked != null) onSelect(picked);
            },
      style: OutlinedButton.styleFrom(
        padding:
            const EdgeInsets.symmetric(horizontal: FwLayout.s3, vertical: 8),
        side: BorderSide(color: t.line),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(Icons.hub_outlined, size: 13, color: t.inkFaint),
        const SizedBox(width: FwLayout.s2),
        Text(current ?? 'No model',
            style: fwMono(t, size: 12.5, color: t.inkSoft)),
        const SizedBox(width: 4),
        Icon(Icons.expand_more_rounded, size: 15, color: t.inkFaint),
      ]),
    );
  }
}

/// Opens the searchable picker and returns the chosen endpoint name (or null).
Future<String?> showModelPicker(
    BuildContext context, List<EndpointRow> endpoints, String? current) {
  return showDialog<String>(
    context: context,
    builder: (_) => _ModelPickerDialog(endpoints: endpoints, current: current),
  );
}

class _ModelPickerDialog extends StatefulWidget {
  final List<EndpointRow> endpoints;
  final String? current;
  const _ModelPickerDialog({required this.endpoints, required this.current});

  @override
  State<_ModelPickerDialog> createState() => _ModelPickerDialogState();
}

class _ModelPickerDialogState extends State<_ModelPickerDialog> {
  String _query = '';

  List<EndpointRow> get _filtered {
    final q = _query.trim().toLowerCase();
    if (q.isEmpty) return widget.endpoints;
    return widget.endpoints
        .where((e) =>
            e.name.toLowerCase().contains(q) ||
            e.backend.toLowerCase().contains(q) ||
            e.providerRole.toLowerCase().contains(q))
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final rows = _filtered;
    return Dialog(
      backgroundColor: t.ground,
      shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(FwLayout.radius),
          side: BorderSide(color: t.line)),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 460, maxHeight: 520),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(
                FwLayout.s4, FwLayout.s4, FwLayout.s4, FwLayout.s3),
            child: TextField(
              autofocus: true,
              onChanged: (v) => setState(() => _query = v),
              style: TextStyle(fontSize: 14, color: t.ink),
              decoration: InputDecoration(
                isDense: true,
                prefixIcon: Icon(Icons.search_rounded, size: 18, color: t.inkFaint),
                hintText: 'Search models…',
                hintStyle: TextStyle(color: t.inkFaint, fontSize: 14),
                border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(FwLayout.radiusSmall)),
              ),
            ),
          ),
          Divider(height: 1, color: t.hairline),
          Flexible(
            child: rows.isEmpty
                ? Padding(
                    padding: const EdgeInsets.all(FwLayout.s5),
                    child: Text('No model matches "$_query".',
                        style: TextStyle(color: t.inkFaint, fontSize: 13)),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.symmetric(vertical: FwLayout.s2),
                    itemCount: rows.length,
                    itemBuilder: (_, i) =>
                        _row(t, rows[i], rows[i].name == widget.current),
                  ),
          ),
        ]),
      ),
    );
  }

  Widget _row(FwTokens t, EndpointRow e, bool selected) {
    final (label, color) = switch (e.credential) {
      'present' || 'cli-auth' => ('ready', t.verified),
      'local-none' => ('local', t.verified),
      _ => ('no key', t.inkFaint),
    };
    return InkWell(
      onTap: () => Navigator.of(context).pop(e.name),
      child: Container(
        padding: const EdgeInsets.symmetric(
            horizontal: FwLayout.s4, vertical: FwLayout.s3),
        color: selected ? t.panel : null,
        child: Row(children: [
          Icon(selected ? Icons.check_rounded : Icons.hub_outlined,
              size: 15, color: selected ? t.ink : t.inkFaint),
          const SizedBox(width: FwLayout.s3),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(e.name,
                    style: TextStyle(
                        fontSize: 13.5,
                        color: t.ink,
                        fontWeight:
                            selected ? FontWeight.w600 : FontWeight.w500)),
                if (e.providerRole.isNotEmpty || e.backend.isNotEmpty)
                  Text(e.providerRole.isNotEmpty ? e.providerRole : e.backend,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: fwMono(t, size: 10.5, color: t.inkFaint)),
              ],
            ),
          ),
          Container(
            width: 6,
            height: 6,
            margin: const EdgeInsets.only(right: 6),
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          Text(label, style: fwMono(t, size: 10.5, color: color)),
        ]),
      ),
    );
  }
}
