// marketplace_panel.dart — the curated catalog: real public MCP servers,
// one-step install into the plugin registry. Credential requirements show
// as env var names only; nothing downloads or runs at install time.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class MarketplacePanel extends StatelessWidget {
  final Map<String, dynamic> doc;
  final Future<void> Function(String name) onInstall;
  final Future<void> Function(String name)? onRemoveEntry;
  const MarketplacePanel(
      {super.key,
      required this.doc,
      required this.onInstall,
      this.onRemoveEntry});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final entries = ((doc['entries'] ?? []) as List)
        .whereType<Map<String, dynamic>>()
        .toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('${doc['note'] ?? ''}',
            style: TextStyle(fontSize: 11.5, color: t.inkFaint)),
        const SizedBox(height: FwLayout.s3),
        HairlineCard(
          padding: const EdgeInsets.symmetric(
              horizontal: FwLayout.s4, vertical: FwLayout.s2),
          child: Column(
            children: [for (final e in entries) _entry(t, e)],
          ),
        ),
      ],
    );
  }

  Widget _entry(FwTokens t, Map<String, dynamic> e) {
    final installed = e['installed'] == true;
    final name = '${e['name']}';
    final command = (e['command'] is List)
        ? (e['command'] as List).join(' ')
        : '';
    return Container(
      padding: const EdgeInsets.symmetric(vertical: FwLayout.s2 + 2),
      decoration: BoxDecoration(
          border: Border(bottom: BorderSide(color: t.hairline))),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(name,
                        style: const TextStyle(
                            fontSize: 13.5, fontWeight: FontWeight.w600)),
                    const SizedBox(width: FwLayout.s2),
                    if (e['origin'] == 'user')
                      const VerdictPill('yours', status: 'unverifiable'),
                    if ('${e['credential_note'] ?? ''}'.isNotEmpty) ...[
                      const SizedBox(width: FwLayout.s2),
                      const VerdictPill('key needed', status: 'unverifiable'),
                    ],
                  ],
                ),
                Text('${e['detail'] ?? ''}',
                    style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
                Text(command, style: fwMono(t, size: 11, color: t.inkFaint)),
                if ('${e['credential_note'] ?? ''}'.isNotEmpty)
                  Text('${e['credential_note']}',
                      style: fwMono(t, size: 11, color: t.inkFaint)),
              ],
            ),
          ),
          const SizedBox(width: FwLayout.s3),
          if (e['origin'] == 'user' && onRemoveEntry != null) ...[
            TextButton(
              onPressed: () => onRemoveEntry!(name),
              child: const Text('Remove'),
            ),
            const SizedBox(width: FwLayout.s2),
          ],
          if (installed)
            const VerdictPill('installed', status: 'verified')
          else
            OutlinedButton(
              onPressed: () => onInstall(name),
              child: const Text('Install'),
            ),
        ],
      ),
    );
  }
}

/// Publish your own server into the catalog: a name, the launch command,
/// and the env var NAMES it needs. Values never leave the environment.
class MarketplaceAddCard extends StatefulWidget {
  final Future<Map<String, dynamic>> Function(
          String name, List<String> command, String detail, List<String> requires)
      onAdd;
  const MarketplaceAddCard({super.key, required this.onAdd});

  @override
  State<MarketplaceAddCard> createState() => _MarketplaceAddCardState();
}

class _MarketplaceAddCardState extends State<MarketplaceAddCard> {
  final _name = TextEditingController();
  final _command = TextEditingController();
  final _detail = TextEditingController();
  final _requires = TextEditingController();
  String? _result;
  bool _ok = false, _busy = false;

  @override
  void dispose() {
    _name.dispose();
    _command.dispose();
    _detail.dispose();
    _requires.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final name = _name.text.trim();
    final argv = _command.text.trim().split(RegExp(r'\s+'));
    if (name.isEmpty || argv.isEmpty || argv.first.isEmpty || _busy) return;
    setState(() => _busy = true);
    try {
      final r = await widget.onAdd(
          name,
          argv,
          _detail.text.trim(),
          _requires.text
              .split(',')
              .map((s) => s.trim())
              .where((s) => s.isNotEmpty)
              .toList());
      setState(() {
        _ok = r['added'] == true;
        _result = _ok
            ? 'saved to your catalog: $name'
            : '${r['error'] ?? 'not saved'}';
        if (_ok) {
          _name.clear();
          _command.clear();
          _detail.clear();
          _requires.clear();
        }
      });
    } catch (e) {
      setState(() {
        _ok = false;
        _result = '$e';
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Add your own server',
              style:
                  const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600)),
          const SizedBox(height: FwLayout.s2),
          Text(
              'Saved to your catalog (~/.flywheel/catalog.json) and shown '
              'beside the curated entries. Nothing runs until you install '
              'and probe it.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            Expanded(
              child: TextField(
                controller: _name,
                style: const TextStyle(fontSize: 12.5),
                decoration: const InputDecoration(hintText: 'name'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            Expanded(
              flex: 2,
              child: TextField(
                controller: _command,
                style: const TextStyle(fontSize: 12.5),
                decoration: const InputDecoration(
                    hintText: 'launch command, e.g. npx -y my-mcp-server'),
              ),
            ),
          ]),
          const SizedBox(height: FwLayout.s2),
          Row(children: [
            Expanded(
              flex: 2,
              child: TextField(
                controller: _detail,
                style: const TextStyle(fontSize: 12.5),
                decoration:
                    const InputDecoration(hintText: 'what it does (optional)'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            Expanded(
              child: TextField(
                controller: _requires,
                style: const TextStyle(fontSize: 12.5),
                decoration: const InputDecoration(
                    hintText: 'env var names, comma-separated'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            FilledButton(
              onPressed: _busy ? null : _submit,
              child: Text(_busy ? 'Saving…' : 'Save'),
            ),
          ]),
          if (_result != null) ...[
            const SizedBox(height: FwLayout.s2),
            _ok
                ? Row(children: [
                    const VerdictPill('saved', status: 'verified'),
                    const SizedBox(width: FwLayout.s2),
                    Expanded(
                        child: Text(_result!,
                            style: TextStyle(
                                fontSize: 12, color: t.inkMuted))),
                  ])
                : HonestNull(_result!),
          ],
        ],
      ),
    );
  }
}
