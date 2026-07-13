// keys_panel.dart — provider credentials, handled the only acceptable way:
// typed once into an obscured field, stored in the OS keychain, shown
// forever after as presence and source only. No value is ever displayed,
// logged, or echoed back.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class KeysPanel extends StatefulWidget {
  final Map<String, dynamic> doc;
  final Future<Map<String, dynamic>> Function(String name, String value) onSet;
  final Future<Map<String, dynamic>> Function(String name) onDelete;
  final VoidCallback onChanged;
  const KeysPanel(
      {super.key,
      required this.doc,
      required this.onSet,
      required this.onDelete,
      required this.onChanged});

  @override
  State<KeysPanel> createState() => _KeysPanelState();
}

class _KeysPanelState extends State<KeysPanel> {
  String? _editing;
  final _value = TextEditingController();
  String? _note;

  @override
  void dispose() {
    _value.dispose();
    super.dispose();
  }

  Future<void> _save(String name) async {
    final v = _value.text;
    if (v.isEmpty) return;
    final r = await widget.onSet(name, v);
    _value.clear(); // the secret leaves this widget immediately
    setState(() {
      _editing = null;
      _note = r['error'] != null ? '${r['error']}' : 'stored $name';
    });
    widget.onChanged();
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final entries = ((widget.doc['entries'] ?? []) as List)
        .whereType<Map<String, dynamic>>()
        .toList();
    final available = widget.doc['available'] == true;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('${widget.doc['note'] ?? ''}',
            style: TextStyle(fontSize: 11.5, color: t.inkFaint)),
        if (!available) ...[
          const SizedBox(height: FwLayout.s2),
          const HonestNull(
              'No supported OS credential store on this platform; the '
              'environment variables keep working.'),
        ],
        if (_note != null) ...[
          const SizedBox(height: FwLayout.s2),
          Text(_note!, style: fwMono(t, size: 10.5, color: t.inkMuted)),
        ],
        const SizedBox(height: FwLayout.s3),
        HairlineCard(
          padding: const EdgeInsets.symmetric(
              horizontal: FwLayout.s4, vertical: FwLayout.s2),
          child: Column(
            children: [for (final e in entries) _row(t, e, available)],
          ),
        ),
      ],
    );
  }

  Widget _row(FwTokens t, Map<String, dynamic> e, bool available) {
    final name = '${e['name']}';
    final source = '${e['source']}';
    final editing = _editing == name;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: FwLayout.s2),
      decoration: BoxDecoration(
          border: Border(bottom: BorderSide(color: t.hairline))),
      child: Row(
        children: [
          Expanded(child: Text(name, style: fwMono(t, size: 11.5))),
          if (editing) ...[
            SizedBox(
              width: 220,
              child: TextField(
                controller: _value,
                obscureText: true,
                autofocus: true,
                style: fwMono(t, size: 12),
                decoration:
                    const InputDecoration(hintText: 'paste key, stores on enter'),
                onSubmitted: (_) => _save(name),
              ),
            ),
            const SizedBox(width: FwLayout.s2),
            OutlinedButton(
              onPressed: () => setState(() {
                _editing = null;
                _value.clear();
              }),
              child: const Text('Cancel'),
            ),
          ] else ...[
            VerdictPill(
                switch (source) {
                  'env' => 'env',
                  'keychain' => 'keychain',
                  _ => 'absent',
                },
                status: source == 'absent' ? 'absent' : 'verified'),
            const SizedBox(width: FwLayout.s2),
            if (available)
              OutlinedButton(
                onPressed: () => setState(() => _editing = name),
                child: const Text('Set'),
              ),
            if (source == 'keychain') ...[
              const SizedBox(width: FwLayout.s2),
              OutlinedButton(
                onPressed: () async {
                  final r = await widget.onDelete(name);
                  setState(() => _note =
                      r['error'] != null ? '${r['error']}' : 'removed $name');
                  widget.onChanged();
                },
                child: const Text('Remove'),
              ),
            ],
          ],
        ],
      ),
    );
  }
}
