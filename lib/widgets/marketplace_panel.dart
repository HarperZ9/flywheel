// marketplace_panel.dart — the curated catalog: real public MCP servers,
// one-step install into the plugin registry. Credential requirements show
// as env var names only; nothing downloads or runs at install time.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class MarketplacePanel extends StatelessWidget {
  final Map<String, dynamic> doc;
  final Future<void> Function(String name) onInstall;
  const MarketplacePanel(
      {super.key, required this.doc, required this.onInstall});

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
                    if ('${e['credential_note'] ?? ''}'.isNotEmpty)
                      VerdictPill('key needed', status: 'unverifiable'),
                  ],
                ),
                Text('${e['detail'] ?? ''}',
                    style: TextStyle(fontSize: 12, color: t.inkMuted)),
                Text(command, style: fwMono(t, size: 10.5, color: t.inkFaint)),
                if ('${e['credential_note'] ?? ''}'.isNotEmpty)
                  Text('${e['credential_note']}',
                      style: fwMono(t, size: 10.5, color: t.inkFaint)),
              ],
            ),
          ),
          const SizedBox(width: FwLayout.s3),
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
