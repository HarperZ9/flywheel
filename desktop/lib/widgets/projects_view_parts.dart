import 'dart:async';

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'project_panels.dart';

class ProjectsAuditSection extends StatelessWidget {
  final bool open;
  final List<Map<String, dynamic>>? entries;
  final VoidCallback onToggle;
  const ProjectsAuditSection({
    super.key,
    required this.open,
    required this.entries,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: onToggle,
          child: Row(
            children: [
              Icon(
                open ? Icons.expand_less : Icons.expand_more,
                size: 16,
                color: t.inkFaint,
              ),
              const SizedBox(width: FwLayout.s1),
              Text(
                'Audit trail',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: t.ink,
                ),
              ),
              const Spacer(),
              if (entries != null)
                Text(
                  '${entries!.length} entries',
                  style: fwMono(t, size: 10.5, color: t.inkFaint),
                ),
            ],
          ),
        ),
        if (open) ...[
          const SizedBox(height: FwLayout.s2),
          if (entries == null)
            const Center(child: CircularProgressIndicator(strokeWidth: 2))
          else if (entries!.isEmpty)
            const HonestNull('No audit entries recorded yet.')
          else
            for (final entry in entries!) AuditRow(entry: entry),
        ],
      ],
    );
  }
}

class ProjectRowCard extends StatelessWidget {
  final Map<String, dynamic> project;
  final String? selectedRoot;
  final bool indexBusy;
  final Future<void> Function(String root) onIndex;
  final Future<void> Function(String root) onRemove;
  const ProjectRowCard({
    super.key,
    required this.project,
    required this.selectedRoot,
    required this.indexBusy,
    required this.onIndex,
    required this.onRemove,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final root = '${project['root']}';
    final exists = project['exists'] == true;
    final selected = root == selectedRoot;
    return Padding(
      padding: const EdgeInsets.only(bottom: FwLayout.s3),
      child: HairlineCard(
        recessed: selected,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    '${project['name']}',
                    style: const TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                VerdictPill('${project['kind']}', status: 'unverifiable'),
                const SizedBox(width: FwLayout.s2),
                VerdictPill(
                  exists ? 'present' : 'missing',
                  status: exists ? 'verified' : 'drift',
                ),
              ],
            ),
            const SizedBox(height: FwLayout.s1),
            Text(root, style: fwMono(t, size: 11, color: t.inkFaint)),
            const SizedBox(height: FwLayout.s3),
            Row(
              children: [
                FilledButton.tonal(
                  onPressed: exists ? () => unawaited(onIndex(root)) : null,
                  child: Text(selected && indexBusy ? 'Indexing…' : 'Index'),
                ),
                const SizedBox(width: FwLayout.s3),
                OutlinedButton(
                  onPressed: () => unawaited(onRemove(root)),
                  child: const Text('Remove'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
