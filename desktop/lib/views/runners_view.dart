// runners_view.dart -- the Runners destination: the machines the
// operator owns, and the work they hold.
//
// A pool page is easy to draw as a list of green dots. The two numbers
// that make it mean something sit in the headline instead: leases that
// lapsed, which is how a pool losing machines looks different from a
// pool that is merely busy, and the chain verdict, which is what
// separates this from a dashboard reporting whatever it was last told.
//
// Membership is settled by a ticket. Minting one is the operator's act
// and it is on this page; enrolling, claiming and completing are the
// machines' own and are not, because a console performing them would be
// reporting on a pool it had joined.
import 'package:flutter/material.dart';

import '../client/gateway_error.dart';
import '../client/gateway_runners.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import 'runners_rows.dart';

class RunnersView extends StatefulWidget {
  final RunnersApi api;
  final bool alive;
  const RunnersView({super.key, required this.api, required this.alive});

  @override
  State<RunnersView> createState() => _RunnersViewState();
}

class _RunnersViewState extends State<RunnersView> {
  final _ticketId = TextEditingController();
  final _labels = TextEditingController();
  Map<String, dynamic>? _roster;
  String? _refused;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    if (widget.alive) _refresh();
  }

  @override
  void dispose() {
    _ticketId.dispose();
    _labels.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    setState(() => _busy = true);
    try {
      final body = await widget.api.roster();
      setState(() {
        _roster = body;
        _error = null;
      });
    } on GatewayException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error = 'the pool could not be read');
    } finally {
      setState(() => _busy = false);
    }
  }

  Future<void> _write(Future<Map<String, dynamic>> Function() verb) async {
    setState(() => _busy = true);
    try {
      final body = await verb();
      setState(() {
        _refused = body['accepted'] == false ? '${body['refused']}' : null;
        _error = null;
      });
    } on GatewayException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error = 'the pool did not accept that');
    } finally {
      setState(() => _busy = false);
    }
    await _refresh();
  }

  void _mint() {
    final labels = _labels.text
        .split(',')
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toList();
    _write(() => widget.api
        .mintTicket(ticketId: _ticketId.text.trim(), labels: labels));
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty('The engine is offline. Start it to read the pool.',
          command: 'flywheel up');
    }
    final t = context.fw;
    return ViewScroll(storageKey: 'runners', children: [
      Row(children: [
        const Expanded(
            child: SectionHeader('Runners', kicker: 'self-hosted pool')),
        IconButton(
          key: const Key('runners-refresh'),
          onPressed: _busy ? null : _refresh,
          tooltip: 'Re-read the pool',
          icon: const Icon(Icons.refresh),
        ),
      ]),
      const SizedBox(height: FwLayout.s3),
      Text(
        'A machine joins by spending a ticket somebody else wrote, and '
        'may advertise only the labels that ticket granted. Enrolments, '
        'dispatches and leases each cite the record before them, so an '
        'edited row breaks the chain at the row after it. What this does '
        'not claim is attestation: a compromised host holding a real '
        'ticket is a real member.',
        style: TextStyle(fontSize: 13, height: 1.5, color: t.inkMuted),
      ),
      const SizedBox(height: FwLayout.s4),
      if (_error != null)
        Padding(
          padding: const EdgeInsets.only(bottom: FwLayout.s3),
          child: HonestNull(_error!),
        ),
      if (_refused != null)
        Padding(
          padding: const EdgeInsets.only(bottom: FwLayout.s3),
          child: HonestNull('Refused: $_refused'),
        ),
      if (_roster != null) ...[
        _headline(),
        const SizedBox(height: FwLayout.s3),
        // A history that stopped verifying is not a pool report. Drawing
        // the rows anyway would present unverified membership as fact,
        // and the engine refuses to append onto it either way.
        if (_roster!['chain_intact'] != true)
          const HonestNull('The pool history no longer verifies, so the '
              'rows are withheld and nothing further is appended.')
        else ...[
          HairlineCard(child: _mintForm(context)),
          const SizedBox(height: FwLayout.s3),
          HairlineCard(
              child: RunnersMachines(
            rows: _rows('runners'),
            busy: _busy,
            onRetire: (id) => _write(() => widget.api.retire(runnerId: id)),
          )),
          const SizedBox(height: FwLayout.s3),
          HairlineCard(child: RunnersWork(rows: _rows('jobs'))),
        ],
      ],
    ]);
  }

  Widget _headline() {
    final runners = _rows('runners');
    final enrolled = runners.where((r) => r['enrolled'] == true).length;
    final lapsed = _int(_roster?['leases_lapsed']);
    final intact = _roster?['chain_intact'] == true;
    return Wrap(spacing: FwLayout.s3, runSpacing: FwLayout.s3, children: [
      StatTile(
          label: 'Chain',
          value: intact ? 'intact' : 'broken',
          status: intact ? 'verified' : 'drift'),
      StatTile(label: 'Enrolled', value: '$enrolled'),
      StatTile(label: 'Queued', value: '${_int(_roster?['queued'])}'),
      StatTile(label: 'Leased', value: '${_int(_roster?['leased'])}'),
      // A lease lapses against the clock, so nothing is running to write
      // the moment it does. The count is the only sign a machine stopped
      // answering rather than the work being slow.
      StatTile(
          label: 'Leases lapsed',
          value: '$lapsed',
          status: lapsed == 0 ? null : 'drift'),
      StatTile(
          label: 'Tickets unspent',
          value: '${_int(_roster?['tickets_unspent'])}'),
    ]);
  }

  Widget _mintForm(BuildContext context) {
    final t = context.fw;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('Write a ticket'),
      const SizedBox(height: FwLayout.s2),
      Text(
        'The labels granted here are the ceiling on what the machine that '
        'spends this ticket may advertise.',
        style: TextStyle(fontSize: 12.5, color: t.inkMuted),
      ),
      const SizedBox(height: FwLayout.s3),
      TextField(
        key: const Key('runners-ticket-id'),
        controller: _ticketId,
        decoration: const InputDecoration(labelText: 'Ticket id'),
      ),
      const SizedBox(height: FwLayout.s2),
      TextField(
        key: const Key('runners-ticket-labels'),
        controller: _labels,
        decoration: const InputDecoration(
            labelText: 'Labels the ticket grants, comma separated'),
      ),
      const SizedBox(height: FwLayout.s2),
      Align(
        alignment: Alignment.centerRight,
        child: TextButton(
          key: const Key('runners-mint'),
          onPressed: _busy ? null : _mint,
          child: const Text('Mint the ticket'),
        ),
      ),
    ]);
  }

  List<Map<String, dynamic>> _rows(String key) =>
      ((_roster?[key] as List?) ?? const [])
          .whereType<Map>()
          .map((m) => m.map((k, v) => MapEntry(k.toString(), v)))
          .toList();
}

int _int(Object? value) => value is num ? value.toInt() : 0;
