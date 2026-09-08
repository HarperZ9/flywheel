// project_panels.dart — the index (catalog + knowledge graph) and store
// (verifiable substrate) panels the Projects view renders. Split out to hold
// the size gate.

import 'package:flutter/material.dart';

import '../models/index_workspace_map.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class IndexPanel extends StatelessWidget {
  final Map<String, dynamic>? summary;
  final IndexWorkspaceMapJob? job;
  final bool busy;
  final String? message;
  final Future<void> Function() onCancel;
  final Future<void> Function() onRefresh;
  final Future<void> Function() onResult;
  final Future<void> Function()? onResume;
  final Future<void> Function()? onUpdate;
  const IndexPanel({
    super.key,
    required this.summary,
    required this.job,
    required this.busy,
    required this.onCancel,
    required this.onRefresh,
    required this.onResult,
    this.onResume,
    this.onUpdate,
    this.message,
  });

  @override
  Widget build(BuildContext context) {
    if (busy && summary == null && job == null) {
      return const Center(child: CircularProgressIndicator(strokeWidth: 2));
    }
    final ix = summary;
    if (ix == null && job == null) return const SizedBox();
    final errors = ix == null ? const {} : (ix['errors'] ?? {}) as Map;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (ix != null) ...[
          AdaptiveTiles(
            children: [
              StatTile(
                label: 'repositories',
                value: '${ix['repo_count'] ?? 0}',
              ),
              StatTile(label: 'classes', value: '${ix['class_total'] ?? 0}'),
              StatTile(
                label: 'dirty',
                value: '${ix['dirty_count'] ?? 0}',
                status: (ix['dirty_count'] ?? 0) == 0 ? 'verified' : 'drift',
              ),
            ],
          ),
          const SizedBox(height: FwLayout.s3),
        ],
        if (job != null)
          _JobRow(
            job!,
            busy,
            onCancel,
            onRefresh,
            onResult,
            onResume,
            onUpdate,
          ),
        if (message != null && message!.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull(message!),
        ],
        if (errors.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull(
            'Index partial: '
            '${errors.entries.map((e) => '${e.key}: ${e.value}').join(' · ')}',
          ),
        ],
        if (job?.content != null) ...[
          const SizedBox(height: FwLayout.s3),
          SelectableText(
            job!.content!,
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
        if ('${ix?['root_sha256_prefix'] ?? job?.rootSha256Prefix ?? ''}'
            .isNotEmpty) ...[
          const SizedBox(height: FwLayout.s3),
          HashText(
            'root',
            '${ix?['root_sha256_prefix'] ?? job?.rootSha256Prefix}',
            keep: 24,
          ),
        ],
      ],
    );
  }
}

class _JobRow extends StatelessWidget {
  final IndexWorkspaceMapJob job;
  final bool busy;
  final Future<void> Function() onCancel, onRefresh, onResult;
  final Future<void> Function()? onResume;
  final Future<void> Function()? onUpdate;
  const _JobRow(
    this.job,
    this.busy,
    this.onCancel,
    this.onRefresh,
    this.onResult,
    this.onResume,
    this.onUpdate,
  );

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      recessed: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              VerdictDot(job.complete ? 'verified' : 'unverifiable', size: 7),
              const SizedBox(width: FwLayout.s2),
              Text(job.displayPhase, style: fwMono(t, size: 12, color: t.ink)),
              const SizedBox(width: FwLayout.s3),
              Text(
                job.progressLabel,
                style: fwMono(t, size: 11, color: t.inkFaint),
              ),
              const Spacer(),
              IconButton(
                tooltip: 'Refresh workspace map',
                onPressed: busy ? null : onRefresh,
                icon: const Icon(Icons.refresh, size: 18),
              ),
              if (job.cancellable)
                IconButton(
                  key: const ValueKey('index-job-cancel'),
                  tooltip: 'Cancel workspace map',
                  onPressed: busy ? null : onCancel,
                  icon: const Icon(Icons.stop_circle_outlined, size: 18),
                ),
              if (job.resultAvailable)
                IconButton(
                  key: const ValueKey('index-job-result'),
                  tooltip: 'Retrieve workspace map result',
                  onPressed: busy ? null : onResult,
                  icon: const Icon(Icons.article_outlined, size: 18),
                ),
              if (job.complete && onUpdate != null)
                IconButton(
                  key: const ValueKey('index-job-update'),
                  tooltip: 'Update workspace map',
                  onPressed: busy ? null : onUpdate,
                  icon: const Icon(Icons.sync, size: 18),
                ),
              if (job.resumable && onResume != null)
                IconButton(
                  key: const ValueKey('index-job-resume'),
                  tooltip: 'Resume workspace map',
                  onPressed: busy ? null : onResume,
                  icon: const Icon(Icons.play_circle_outline, size: 18),
                ),
            ],
          ),
          if (job.complete) ...[
            const SizedBox(height: FwLayout.s2),
            Text(
              'Completed result is a snapshot. Run Update workspace map '
              'to validate current source after edits.',
              style: TextStyle(fontSize: 11.5, color: t.inkFaint),
            ),
          ],
          if (job.resultSha256 != null)
            HashText('result', job.resultSha256!, keep: 24),
        ],
      ),
    );
  }
}

class AuditRow extends StatelessWidget {
  final Map<String, dynamic> entry;
  const AuditRow({super.key, required this.entry});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final kind = '${entry['kind'] ?? ''}';
    final hash = '${entry['hash'] ?? ''}';
    final ts = '${entry['ts'] ?? ''}';
    return Container(
      padding: const EdgeInsets.symmetric(vertical: FwLayout.s1),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: t.hairline)),
      ),
      child: Row(
        children: [
          VerdictDot('verified', size: 6),
          const SizedBox(width: FwLayout.s2),
          Text(kind, style: fwMono(t, size: 11, color: t.ink)),
          const Spacer(),
          if (hash.isNotEmpty) HashText('', hash, keep: 12),
          const SizedBox(width: FwLayout.s3),
          if (ts.isNotEmpty)
            Text(ts, style: fwMono(t, size: 10, color: t.inkFaint)),
        ],
      ),
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
        AdaptiveTiles(
          children: [
            StatTile(label: 'entities', value: '${store['entities'] ?? 0}'),
            StatTile(label: 'relations', value: '${store['relations'] ?? 0}'),
            StatTile(
              label: 'audit entries',
              value: '${store['audit_entries'] ?? 0}',
            ),
          ],
        ),
        const SizedBox(height: FwLayout.s3),
        Row(
          children: [
            Expanded(
              child: Text(
                '${store['note'] ?? ''}',
                style: TextStyle(fontSize: 11.5, color: t.inkFaint),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            OutlinedButton(
              onPressed: onVerify,
              child: const Text('Verify chain'),
            ),
          ],
        ),
      ],
    );
  }
}
