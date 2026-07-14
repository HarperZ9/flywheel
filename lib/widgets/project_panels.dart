// project_panels.dart — the index (catalog + knowledge graph) and store
// (verifiable substrate) panels the Projects view renders. Split out to hold
// the size gate.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class IndexPanel extends StatelessWidget {
  final Map<String, dynamic>? index;
  final bool indexing;
  const IndexPanel({super.key, required this.index, required this.indexing});

  @override
  Widget build(BuildContext context) {
    if (indexing) {
      return const Center(child: CircularProgressIndicator(strokeWidth: 2));
    }
    final ix = index;
    if (ix == null) return const SizedBox();
    final errors = (ix['errors'] ?? {}) as Map;
    return Column(
      children: [
        Row(
          children: [
            Expanded(
                child: StatTile(
                    label: 'repositories', value: '${ix['repo_count'] ?? 0}')),
            const SizedBox(width: FwLayout.s3),
            Expanded(
                child: StatTile(
                    label: 'classes', value: '${ix['class_total'] ?? 0}')),
            const SizedBox(width: FwLayout.s3),
            Expanded(
                child: StatTile(
                    label: 'dirty',
                    value: '${ix['dirty_count'] ?? 0}',
                    status:
                        (ix['dirty_count'] ?? 0) == 0 ? 'verified' : 'drift')),
          ],
        ),
        const SizedBox(height: FwLayout.s3),
        Row(
          children: [
            Expanded(
                child: StatTile(
                    label: 'graph relations',
                    value: '${ix['relation_count'] ?? 0}')),
            const SizedBox(width: FwLayout.s3),
            Expanded(
                child: StatTile(
                    label: 'roles', value: '${ix['role_count'] ?? 0}')),
            const SizedBox(width: FwLayout.s3),
            Expanded(
                child: StatTile(
                    label: 'cycles',
                    value: '${ix['cycle_count'] ?? 0}',
                    status:
                        (ix['cycle_count'] ?? 0) == 0 ? 'verified' : 'drift')),
          ],
        ),
        if (errors.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull('Index partial: '
              '${errors.entries.map((e) => '${e.key}: ${e.value}').join(' · ')}'),
        ],
        if ('${ix['root_sha256_prefix'] ?? ''}'.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s3),
          HashText('root', '${ix['root_sha256_prefix']}', keep: 24),
        ],
      ],
    );
  }
}

class StorePanel extends StatelessWidget {
  final Map<String, dynamic> store;
  final Future<void> Function() onVerify;
  const StorePanel({super.key, required this.store, required this.onVerify});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(
      children: [
        Row(
          children: [
            Expanded(
                child: StatTile(
                    label: 'entities', value: '${store['entities'] ?? 0}')),
            const SizedBox(width: FwLayout.s3),
            Expanded(
                child: StatTile(
                    label: 'relations', value: '${store['relations'] ?? 0}')),
            const SizedBox(width: FwLayout.s3),
            Expanded(
                child: StatTile(
                    label: 'audit entries',
                    value: '${store['audit_entries'] ?? 0}')),
          ],
        ),
        const SizedBox(height: FwLayout.s3),
        Row(
          children: [
            Expanded(
              child: Text('${store['note'] ?? ''}',
                  style: TextStyle(fontSize: 11.5, color: t.inkFaint)),
            ),
            const SizedBox(width: FwLayout.s3),
            OutlinedButton(
                onPressed: onVerify, child: const Text('Verify chain')),
          ],
        ),
      ],
    );
  }
}
