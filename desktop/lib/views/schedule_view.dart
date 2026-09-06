// schedule_view.dart -- the Schedule destination: unattended runs, and
// what they owe.
//
// Each row carries the interval, the catch-up policy, how many
// occurrences came due while nothing was running, and whether the fire
// history for that schedule still verifies. A tick is a pull: the button
// asks the engine to evaluate what is owed and hands back what fired and
// what was passed over. The passed-over count is the honest half, so it
// sits beside the fired count rather than under it.
import 'package:flutter/material.dart';

import '../client/gateway_error.dart';
import '../client/gateway_schedule.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class ScheduleView extends StatefulWidget {
  final ScheduleApi api;
  final bool alive;
  const ScheduleView({super.key, required this.api, required this.alive});

  @override
  State<ScheduleView> createState() => _ScheduleViewState();
}

class _ScheduleViewState extends State<ScheduleView> {
  Map<String, dynamic>? _roster;
  List<Map<String, dynamic>> _rows = [];
  Map<String, dynamic>? _tick;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    if (widget.alive) _refresh();
  }

  Future<void> _refresh() async {
    setState(() => _busy = true);
    try {
      final body = await widget.api.roster();
      setState(() {
        _roster = body;
        _rows = _mapList(body['schedules']);
        _error = null;
      });
    } on GatewayException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error = 'the schedule roster could not be read');
    } finally {
      setState(() => _busy = false);
    }
  }

  Future<void> _runDue() async {
    setState(() => _busy = true);
    try {
      final body = await widget.api.tick();
      setState(() {
        _tick = body;
        _error = null;
      });
    } on GatewayException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error = 'the tick did not complete');
    } finally {
      setState(() => _busy = false);
    }
    await _refresh();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. Start it to read the schedule.',
          command: 'flywheel up');
    }
    final t = context.fw;
    return ViewScroll(storageKey: 'schedule', children: [
      Row(children: [
        const Expanded(
            child: SectionHeader('Schedule', kicker: 'unattended runs')),
        TextButton(
          key: const Key('schedule-tick'),
          onPressed: _busy ? null : _runDue,
          child: const Text('Run due work'),
        ),
        IconButton(
          key: const Key('schedule-refresh'),
          onPressed: _busy ? null : _refresh,
          tooltip: 'Re-read the roster',
          icon: const Icon(Icons.refresh),
        ),
      ]),
      const SizedBox(height: FwLayout.s3),
      Text(
        'A tick is a pull, not a daemon. The engine evaluates what came '
        'due, fires what the catch-up policy admits, and names what it '
        'passed over. Each firing cites the one before it, so a deleted '
        'record breaks the chain at the record after it.',
        style: TextStyle(fontSize: 13, height: 1.5, color: t.inkMuted),
      ),
      const SizedBox(height: FwLayout.s4),
      if (_error != null)
        Padding(
          padding: const EdgeInsets.only(bottom: FwLayout.s3),
          child: HonestNull(_error!),
        ),
      if (_roster != null) ...[
        _headline(),
        const SizedBox(height: FwLayout.s3),
        if (_roster!['any_chain_broken'] == true) ...[
          const HonestNull('A fire history no longer verifies. Nothing '
              'further is appended to a broken chain.'),
          const SizedBox(height: FwLayout.s3),
        ],
        HairlineCard(child: _table(context)),
        if (_tick != null) ...[
          const SizedBox(height: FwLayout.s3),
          HairlineCard(child: _tickSummary(context)),
        ],
      ],
    ]);
  }

  Widget _headline() {
    final due = _rows.fold<int>(
        0, (sum, row) => sum + _int((row['pending'] as Map?)?['due']));
    final fires = _rows.fold<int>(0, (sum, row) => sum + _int(row['fires']));
    final broken = _roster?['any_chain_broken'] == true;
    return Wrap(spacing: FwLayout.s3, runSpacing: FwLayout.s3, children: [
      StatTile(label: 'Schedules', value: '${_int(_roster?['count'])}'),
      StatTile(label: 'Due now', value: '$due'),
      StatTile(label: 'Fires recorded', value: '$fires'),
      StatTile(
          label: 'Chain',
          value: broken ? 'broken' : 'intact',
          status: broken ? 'drift' : 'verified'),
    ]);
  }

  Widget _table(BuildContext context) {
    final t = context.fw;
    if (_rows.isEmpty) {
      return const Padding(
        padding: EdgeInsets.all(FwLayout.s3),
        child: HonestNull('No schedules defined. Nothing runs unattended '
            'until one is.'),
      );
    }
    return Padding(
      padding: const EdgeInsets.all(FwLayout.s3),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        for (final row in _rows) ...[
          _row(context, row, t),
          const SizedBox(height: FwLayout.s2),
        ],
      ]),
    );
  }

  Widget _row(BuildContext context, Map<String, dynamic> row, FwTokens t) {
    final schedule = (row['schedule'] as Map?) ?? const {};
    final intact = row['chain_intact'] != false;
    final due = _int((row['pending'] as Map?)?['due']);
    return Row(children: [
      VerdictDot(intact ? 'verified' : 'drift'),
      const SizedBox(width: FwLayout.s2),
      Expanded(
        child: Text('${schedule['schedule_id'] ?? ''}',
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 12, color: t.ink)),
      ),
      Text('${schedule['event'] ?? ''}',
          style: TextStyle(fontSize: 12, color: t.inkMuted)),
      const SizedBox(width: FwLayout.s3),
      Text(_interval(_int(schedule['every_seconds'])),
          style: TextStyle(fontSize: 12, color: t.inkMuted)),
      const SizedBox(width: FwLayout.s3),
      Text('${schedule['catch_up'] ?? ''}',
          style: TextStyle(fontSize: 12, color: t.inkMuted)),
      const SizedBox(width: FwLayout.s3),
      VerdictPill('$due due', status: due == 0 ? 'verified' : 'pending'),
    ]);
  }

  Widget _tickSummary(BuildContext context) {
    final t = context.fw;
    final refused = _mapList(_tick?['results'])
        .where((r) => r['refused'] != null)
        .toList();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('Last tick'),
      const SizedBox(height: FwLayout.s2),
      Text(
        '${_int(_tick?['evaluated'])} evaluated, '
        '${_int(_tick?['fired'])} fired, '
        '${_int(_tick?['skipped'])} passed over at '
        '${_tick?['ticked_at'] ?? ''}',
        style: TextStyle(fontSize: 12.5, color: t.ink),
      ),
      for (final row in refused) ...[
        const SizedBox(height: FwLayout.s2),
        HonestNull('${row['schedule_id']}: ${row['refused']}'),
      ],
    ]);
  }
}

/// Seconds read as a duration a person plans around, and the raw number
/// stays available in the record behind the row.
String _interval(int seconds) {
  if (seconds <= 0) return '';
  if (seconds % 86400 == 0) return 'every ${seconds ~/ 86400}d';
  if (seconds % 3600 == 0) return 'every ${seconds ~/ 3600}h';
  if (seconds % 60 == 0) return 'every ${seconds ~/ 60}m';
  return 'every ${seconds}s';
}

int _int(Object? value) => value is num ? value.toInt() : 0;

List<Map<String, dynamic>> _mapList(Object? value) => value is List
    ? value
        .whereType<Map>()
        .map((m) => m.map((k, v) => MapEntry(k.toString(), v)))
        .toList()
    : <Map<String, dynamic>>[];
