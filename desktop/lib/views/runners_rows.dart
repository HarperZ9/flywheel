// runners_rows.dart -- the two row lists on the Runners page: the
// machines in the pool, and the work they hold.
//
// They sit beside runners_view.dart because the page's own job is the
// headline and the ticket form. These render rows the engine already
// sent and decide nothing themselves.
import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

/// The machines, each with the labels it advertises. Retiring is offered
/// only for a machine still in the pool, since retiring one already out
/// of it would append an event that changes nothing.
class RunnersMachines extends StatelessWidget {
  final List<Map<String, dynamic>> rows;
  final bool busy;
  final void Function(String runnerId) onRetire;

  const RunnersMachines({
    super.key,
    required this.rows,
    required this.busy,
    required this.onRetire,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('Machines'),
      const SizedBox(height: FwLayout.s2),
      if (rows.isEmpty)
        Text('No machine has joined.',
            style: TextStyle(fontSize: 12.5, color: t.ink))
      else
        for (final row in rows) ...[
          _machine(row, t),
          const SizedBox(height: FwLayout.s2),
        ],
    ]);
  }

  Widget _machine(Map<String, dynamic> row, FwTokens t) {
    final id = '${row['runner_id'] ?? ''}';
    final enrolled = row['enrolled'] == true;
    return Row(children: [
      VerdictDot(enrolled ? 'verified' : 'pending'),
      const SizedBox(width: FwLayout.s2),
      Expanded(
        child: Text(id,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 12, color: t.ink)),
      ),
      const SizedBox(width: FwLayout.s3),
      Text(runnerList(row['labels']).join(', '),
          style: TextStyle(fontSize: 12, color: t.inkMuted)),
      const SizedBox(width: FwLayout.s3),
      if (enrolled)
        TextButton(
          key: Key('runners-retire-$id'),
          onPressed: busy ? null : () => onRetire(id),
          child: const Text('Retire'),
        )
      else
        const VerdictPill('retired', status: 'pending'),
    ]);
  }
}

/// The work, each row naming either the labels it still waits on or the
/// machine holding it. A finished job keeps that name, which is the half
/// an auditor reads the row for.
class RunnersWork extends StatelessWidget {
  final List<Map<String, dynamic>> rows;

  const RunnersWork({super.key, required this.rows});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('Work'),
      const SizedBox(height: FwLayout.s2),
      if (rows.isEmpty)
        Text('Nothing dispatched.',
            style: TextStyle(fontSize: 12.5, color: t.ink))
      else
        for (final row in rows) ...[
          _job(row, t),
          const SizedBox(height: FwLayout.s2),
        ],
    ]);
  }

  Widget _job(Map<String, dynamic> row, FwTokens t) {
    return Row(children: [
      VerdictPill('${row['state'] ?? ''}',
          status: _stateStatus('${row['state']}', row['ok'])),
      const SizedBox(width: FwLayout.s2),
      Expanded(
        child: Text('${row['job_id'] ?? ''}',
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 12, color: t.ink)),
      ),
      const SizedBox(width: FwLayout.s3),
      Text(
          row['runner_id'] == null
              ? 'needs ${runnerList(row['requires']).join(', ')}'
              : 'held by ${row['runner_id']}',
          style: TextStyle(fontSize: 12, color: t.inkMuted)),
    ]);
  }

  /// A finished job that failed is not a verified job, so `done` alone
  /// never earns the verified colour.
  String _stateStatus(String state, Object? ok) {
    if (state == 'done') return ok == true ? 'verified' : 'drift';
    return state == 'leased' ? 'live' : 'pending';
  }
}

/// Read a list of strings off a gateway field that may be missing or of
/// the wrong shape, degrading to empty rather than throwing.
List<String> runnerList(Object? value) => value is List
    ? value.map((v) => v.toString()).toList()
    : const <String>[];
