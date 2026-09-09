import 'package:flutter/material.dart';

import '../models/bulletin_media_models.dart';

final class BulletinMediaRunRow extends StatelessWidget {
  final BulletinMediaRun run;
  final bool selected;
  final VoidCallback onTap;

  const BulletinMediaRunRow({
    super.key,
    required this.run,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) => Card(
        child: ListTile(
          key: ValueKey('bulletin-run-${run.runId}'),
          selected: selected,
          title: Text(run.title),
          subtitle: Text(
              '${run.runId} · ${run.status} · ${run.artifactCount} artifacts'),
          trailing: Text(run.kind),
          onTap: onTap,
        ),
      );
}
