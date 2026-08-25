// swarms_view.dart -- the Swarms destination: parallel agent sessions.
//
// One goal fans out to N children under fixed roles whose authority is
// enforced engine-side; every child is sealed a run receipt and fan-in is
// deterministic quorum arithmetic that fires the agent.completed hook event.
// This view is a thin wire over /api/subagents*: it spawns, lists, adopts
// (asking for a detached swarm reattaches it), cancels, and reads receipts.
import 'package:flutter/material.dart';

import '../client/gateway_error.dart';
import '../client/gateway_swarms.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

const _roles = ['explore', 'plan', 'implement', 'verify', 'review'];
const _quorums = ['majority', 'all', 'any'];

class SwarmsView extends StatefulWidget {
  final SwarmsApi api;
  final bool alive;
  const SwarmsView({super.key, required this.api, required this.alive});

  @override
  State<SwarmsView> createState() => _SwarmsViewState();
}

class _SwarmsViewState extends State<SwarmsView> {
  final _goal = TextEditingController();
  final _endpoint = TextEditingController();
  final _selected = <String>{'explore'};
  String _quorum = 'majority';
  List<Map<String, dynamic>> _rows = [];
  Map<String, dynamic>? _detail;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  @override
  void dispose() {
    _goal.dispose();
    _endpoint.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    setState(() => _busy = true);
    try {
      final body = await widget.api.list();
      final rows = body['swarms'];
      setState(() {
        _rows = rows is List
            ? rows.whereType<Map>().map(_asMap).toList()
            : <Map<String, dynamic>>[];
        _error = null;
      });
    } on GatewayException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error = 'the swarm roster could not be read');
    } finally {
      setState(() => _busy = false);
    }
  }

  Future<void> _spawn() async {
    final goal = _goal.text.trim();
    final endpoint = _endpoint.text.trim();
    if (goal.isEmpty || endpoint.isEmpty || _selected.isEmpty) return;
    setState(() => _busy = true);
    try {
      await widget.api.spawn(
        goal: goal,
        endpoint: endpoint,
        children: [
          for (final role in _roles)
            if (_selected.contains(role)) {'role': role}
        ],
        quorumPolicy: _quorum,
      );
      _goal.clear();
      await _refresh();
    } on GatewayException catch (e) {
      setState(() => _error =
          e.statusCode == 422 ? 'the spawn was refused by the engine' : e.message);
    } catch (_) {
      setState(() => _error = 'the spawn could not be issued');
    } finally {
      setState(() => _busy = false);
    }
  }

  Future<void> _cancel(String swarmId) async {
    setState(() => _busy = true);
    try {
      await widget.api.cancel(swarmId);
      await _refresh();
    } on GatewayException catch (e) {
      setState(() =>
          _error = e.statusCode == 409 ? 'that swarm already sealed' : e.message);
    } catch (_) {
      setState(() => _error = 'the cancel could not be issued');
    } finally {
      setState(() => _busy = false);
    }
  }

  Future<void> _open(Map<String, dynamic> row) async {
    final id = row['swarm_id'];
    if (id is! String) return;
    setState(() => _busy = true);
    try {
      final snap = await widget.api.snapshot(id);
      setState(() => _detail = snap);
    } on GatewayException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error = 'the swarm snapshot could not be read');
    } finally {
      setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty('The engine is offline. Start it, then fan out.',
          command: 'flywheel up');
    }
    final t = context.fw;
    return ViewScroll(storageKey: 'swarms', children: [
      const SectionHeader('Subagent swarms', kicker: 'parallel sessions'),
      const SizedBox(height: FwLayout.s3),
      Text(
        'One goal fans out to role-prompted children, each in its own '
        'process tree and workspace under grants its role can hold. Every '
        'child seals a run receipt; quorum decides the verdict; asking for '
        'a detached swarm after a restart reattaches it.',
        style: TextStyle(fontSize: 13, height: 1.5, color: t.inkMuted),
      ),
      const SizedBox(height: FwLayout.s4),
      HairlineCard(child: _spawnForm(context)),
      const SizedBox(height: FwLayout.s4),
      if (_error != null)
        Padding(
          padding: const EdgeInsets.only(bottom: FwLayout.s3),
          child: HonestNull(_error!),
        ),
      if (_rows.isEmpty && !_busy)
        const HonestNull(
            'No swarms yet. Spawn one above; sealed receipts persist here.')
      else
        ..._rows.map((row) => Padding(
              padding: const EdgeInsets.only(bottom: FwLayout.s2),
              child: HairlineCard(child: _rowTile(context, row)),
            )),
      if (_detail != null) ...[
        const SizedBox(height: FwLayout.s4),
        HairlineCard(child: _detailCard(context, _detail!)),
      ],
    ]);
  }

  Widget _spawnForm(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(FwLayout.s3),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        TextField(
          key: const Key('swarm-goal'),
          controller: _goal,
          decoration:
              const InputDecoration(labelText: 'Goal for the swarm'),
        ),
        const SizedBox(height: FwLayout.s2),
        TextField(
          key: const Key('swarm-endpoint'),
          controller: _endpoint,
          decoration: const InputDecoration(
              labelText: 'Endpoint (for example serve or a provider name)'),
        ),
        const SizedBox(height: FwLayout.s2),
        Wrap(
          spacing: FwLayout.s1,
          runSpacing: FwLayout.s1,
          children: [
            for (final role in _roles)
              FilterChip(
                key: Key('swarm-role-$role'),
                label: Text(role),
                selected: _selected.contains(role),
                onSelected: (on) => setState(() =>
                    on ? _selected.add(role) : _selected.remove(role)),
              ),
          ],
        ),
        const SizedBox(height: FwLayout.s2),
        Row(children: [
          DropdownButton<String>(
            key: const Key('swarm-quorum'),
            value: _quorum,
            items: [
              for (final q in _quorums)
                DropdownMenuItem(value: q, child: Text('quorum: $q'))
            ],
            onChanged: (q) => setState(() => _quorum = q ?? _quorum),
          ),
          const Spacer(),
          FilledButton(
            key: const Key('swarm-spawn'),
            onPressed: _busy ? null : _spawn,
            child: const Text('Spawn'),
          ),
        ]),
      ]),
    );
  }

  Widget _rowTile(BuildContext context, Map<String, dynamic> row) {
    final id = row['swarm_id'] ?? '';
    final status = (row['status'] ?? 'unknown').toString();
    final verdict = row['verdict'];
    final done = row['completed'];
    final total = row['total'] ?? row['children'];
    final cancellable = status == 'running' || status == 'detached';
    return Padding(
      padding: const EdgeInsets.all(FwLayout.s3),
      child:
          Row(children: [
        Expanded(
          child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                HashText('Swarm', id.toString()),
                const SizedBox(height: FwLayout.s1),
                Wrap(spacing: FwLayout.s2, crossAxisAlignment:
                    WrapCrossAlignment.center, children: [
                  VerdictPill(status, status: _pillStatus(status)),
                  if (verdict is String)
                    VerdictPill(verdict,
                        status:
                            verdict == 'satisfied' ? 'verified' : 'pending'),
                  if (done is int && total is int)
                    Text('$done of $total children completed',
                        style: const TextStyle(fontSize: 12))
                  else if (total is int)
                    Text('$total children',
                        style: const TextStyle(fontSize: 12)),
                ]),
              ]),
        ),
        TextButton(
            key: Key('swarm-open-$id'),
            onPressed: _busy ? null : () => _open(row),
            child: const Text('Receipts')),
        if (cancellable)
          TextButton(
              key: Key('swarm-cancel-$id'),
              onPressed: _busy ? null : () => _cancel(id as String),
              child: const Text('Cancel')),
      ]),
    );
  }

  Widget _detailCard(BuildContext context, Map<String, dynamic> snap) {
    final t = context.fw;
    final receipt = snap['receipt'];
    final children = receipt is Map && receipt['children'] is List
        ? (receipt['children'] as List).whereType<Map>().map(_asMap).toList()
        : <Map<String, dynamic>>[];
    return Padding(
      padding: const EdgeInsets.all(FwLayout.s3),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Swarm ${snap['swarm_id']}',
            style: TextStyle(
                fontSize: 13,
                color: t.ink,
                fontWeight: FontWeight.w600)),
        const SizedBox(height: FwLayout.s2),
        if (children.isEmpty)
          const HonestNull('No child receipts yet; the swarm is still running.')
        else
          ...children.map((c) => Padding(
                padding: const EdgeInsets.only(bottom: FwLayout.s1),
                child: Row(children: [
                  VerdictDot(_pillStatus('${c['status']}')),
                  const SizedBox(width: FwLayout.s2),
                  Expanded(
                      child: Text('${c['role']} ${c['child_id']}',
                          style:
                              TextStyle(fontSize: 12, color: t.inkSoft))),
                  Text('${c['status']}',
                      style: TextStyle(fontSize: 12, color: t.inkMuted)),
                ]),
              )),
      ]),
    );
  }
}

/// Status maps onto the verdict palette: satisfied children are the accept
/// mark, pending states are unverifiable grey, and failed or cancelled runs
/// take drift -- the caution verdict. No red anywhere in this system.
String _pillStatus(String status) {
  switch (status) {
    case 'completed':
    case 'satisfied':
    case 'sealed':
      return 'verified';
    case 'running':
    case 'detached':
    case 'pending':
    case 'timeout':
      return 'pending';
    default:
      return 'drift';
  }
}

Map<String, dynamic> _asMap(Map<dynamic, dynamic> m) =>
    m.map((k, v) => MapEntry(k.toString(), v));
