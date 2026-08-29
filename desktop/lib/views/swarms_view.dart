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
import '../widgets/swarm_cards.dart';

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
  bool _loaded = false;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  @override
  void didUpdateWidget(SwarmsView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _refresh();
  }

  @override
  void dispose() {
    _goal.dispose();
    _endpoint.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    if (!widget.alive) return;
    setState(() => _busy = true);
    try {
      final body = await widget.api.list();
      final rows = body['swarms'];
      if (!mounted) return;
      setState(() {
        _rows = rows is List
            ? rows.whereType<Map>().map(asSwarmMap).toList()
            : <Map<String, dynamic>>[];
        _error = null;
        _loaded = true;
      });
    } on GatewayException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'the swarm roster could not be read');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
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
      if (!mounted) return;
      _goal.clear();
      await _refresh();
    } on GatewayException catch (e) {
      if (mounted) {
        setState(() => _error = e.statusCode == 422
            ? 'the spawn was refused by the engine'
            : e.message);
      }
    } catch (_) {
      if (mounted) setState(() => _error = 'the spawn could not be issued');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _cancel(String swarmId) async {
    setState(() => _busy = true);
    try {
      await widget.api.cancel(swarmId);
      await _refresh();
    } on GatewayException catch (e) {
      if (mounted) {
        setState(() => _error =
            e.statusCode == 409 ? 'that swarm already sealed' : e.message);
      }
    } catch (_) {
      if (mounted) setState(() => _error = 'the cancel could not be issued');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _open(Map<String, dynamic> row) async {
    final id = row['swarm_id'];
    if (id is! String) return;
    setState(() => _busy = true);
    try {
      final snap = await widget.api.snapshot(id);
      if (mounted) setState(() => _detail = snap);
    } on GatewayException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'the swarm snapshot could not be read');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
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
      SectionHeader('Subagent swarms',
          kicker: 'parallel sessions',
          trailing: IconButton(
            key: const Key('swarms-refresh'),
            onPressed: _busy ? null : _refresh,
            tooltip: 'Re-read the swarm roster',
            icon: const Icon(Icons.refresh),
          )),
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
      if (!_loaded && _busy)
        const Padding(
          padding: EdgeInsets.only(top: FwLayout.s2),
          child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
        )
      else if (_rows.isEmpty && _loaded)
        const HonestNull(
            'No swarms yet. Spawn one above; sealed receipts persist here.')
      else
        ..._rows.map((row) => Padding(
              padding: const EdgeInsets.only(bottom: FwLayout.s2),
              child: HairlineCard(child: SwarmRowTile(
                row: row, busy: _busy, onOpen: _open, onCancel: _cancel,
              )),
            )),
      if (_detail != null) ...[
        const SizedBox(height: FwLayout.s4),
        HairlineCard(child: SwarmDetailCard(snap: _detail!)),
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

}
