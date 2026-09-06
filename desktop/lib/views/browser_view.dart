// browser_view.dart -- the Browser destination: what a run was allowed
// to drive, and what it actually did.
//
// Two counts on this page do the work. `refused` is kept, so a tightly
// bounded run and a run that did nothing do not read alike afterwards.
// `performed` is separate from `admitted`, so an act the policy allowed
// on an engine with no driver bound reads as a decision that was
// recorded rather than a screen that moved.
//
// The page reads and does not act. A session's policy is its chain's
// first record, so opening one from here would fix the rules for a run
// from outside that run.
import 'package:flutter/material.dart';

import '../client/gateway_browser.dart';
import '../client/gateway_error.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

/// The verdicts drawn per session. The counts above them are the
/// engine's and cover every act, so this shortens a list and never a
/// number.
const _actionsShown = 25;

class BrowserView extends StatefulWidget {
  final BrowserApi api;
  final bool alive;
  const BrowserView({super.key, required this.api, required this.alive});

  @override
  State<BrowserView> createState() => _BrowserViewState();
}

class _BrowserViewState extends State<BrowserView> {
  Map<String, dynamic>? _roster;
  Map<String, dynamic>? _session;
  String? _open;
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
        _error = null;
      });
      final ids = _sessions();
      if (ids.isNotEmpty) await _read(ids.contains(_open) ? _open! : ids.first);
    } on GatewayException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error = 'the browser sessions could not be read');
    } finally {
      setState(() => _busy = false);
    }
  }

  Future<void> _read(String runId) async {
    try {
      final body = await widget.api.session(runId);
      setState(() {
        _open = runId;
        _session = body;
        _error = null;
      });
    } on GatewayException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error = 'that session could not be read');
    }
  }

  List<String> _sessions() => ((_roster?['sessions'] as List?) ?? const [])
      .map((v) => v.toString())
      .toList();

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. Start it to read the sessions.',
          command: 'flywheel up');
    }
    final t = context.fw;
    final driver = _roster?['driver'];
    return ViewScroll(storageKey: 'browser', children: [
      Row(children: [
        const Expanded(
            child: SectionHeader('Browser', kicker: 'computer control')),
        IconButton(
          key: const Key('browser-refresh'),
          onPressed: _busy ? null : _refresh,
          tooltip: 'Re-read the sessions',
          icon: const Icon(Icons.refresh),
        ),
      ]),
      const SizedBox(height: FwLayout.s3),
      Text(
        'The policy is the first record of a session, so no act is judged '
        'by rules written after it. Typing into a credential-shaped field '
        'is refused before the policy is consulted, and a non-http scheme '
        'never resolves. Refusals are kept beside the acts they turned '
        'down.',
        style: TextStyle(fontSize: 13, height: 1.5, color: t.inkMuted),
      ),
      const SizedBox(height: FwLayout.s4),
      if (_error != null)
        Padding(
          padding: const EdgeInsets.only(bottom: FwLayout.s3),
          child: HonestNull(_error!),
        ),
      _driverLine(context, driver),
      const SizedBox(height: FwLayout.s3),
      if (_sessions().isEmpty && !_busy)
        const HonestNull('No session has been opened under this run root.')
      else ...[
        _picker(),
        const SizedBox(height: FwLayout.s3),
        if (_session != null) ...[
          _headline(),
          const SizedBox(height: FwLayout.s3),
          HairlineCard(child: _policy(context)),
          const SizedBox(height: FwLayout.s3),
          HairlineCard(child: _verdicts(context)),
        ],
      ],
    ]);
  }

  /// An unbound driver is the honest null this surface exists to keep
  /// visible. Nothing on the page below it moved a screen.
  Widget _driverLine(BuildContext context, Object? driver) => driver == null
      ? const HonestNull('No driver is bound, so the engine decided and '
          'recorded and performed nothing.')
      : Row(children: [
          const VerdictPill('driver bound', status: 'live'),
          const SizedBox(width: FwLayout.s2),
          Text('$driver',
              style:
                  TextStyle(fontSize: 12.5, color: context.fw.inkMuted)),
        ]);

  Widget _picker() => Wrap(
        spacing: FwLayout.s2,
        runSpacing: FwLayout.s2,
        children: [
          for (final id in _sessions())
            ChoiceChip(
              key: Key('browser-session-$id'),
              label: Text(id),
              selected: id == _open,
              onSelected: _busy ? null : (_) => _read(id),
            ),
        ],
      );

  Widget _headline() {
    final intact = _session?['chain_intact'] == true;
    final refused = _int(_session?['refused']);
    return Wrap(spacing: FwLayout.s3, runSpacing: FwLayout.s3, children: [
      StatTile(
          label: 'Chain',
          value: intact ? 'intact' : 'broken',
          status: intact ? 'verified' : 'drift'),
      StatTile(label: 'Attempted', value: '${_int(_session?['attempted'])}'),
      StatTile(label: 'Admitted', value: '${_int(_session?['admitted'])}'),
      StatTile(
          label: 'Refused',
          value: '$refused',
          status: refused == 0 ? null : 'pending'),
      // Separate from admitted on purpose: with no driver bound these
      // differ, and a page printing only one of them would imply a
      // screen moved.
      StatTile(label: 'Performed', value: '${_int(_session?['performed'])}'),
    ]);
  }

  Widget _policy(BuildContext context) {
    final t = context.fw;
    final policy = _asMap(_session?['policy']);
    if (policy == null) {
      return const HonestNull('This session has no policy yet, so nothing '
          'may be attempted in it.');
    }
    final refuseKinds = _list(policy['refuse_kinds']);
    final cap = policy['max_actions'];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('The rules, written first'),
      const SizedBox(height: FwLayout.s2),
      Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
        for (final origin in _list(policy['origins']))
          VerdictPill(origin, status: 'verified'),
        for (final kind in refuseKinds) VerdictPill(kind, status: 'drift'),
      ]),
      const SizedBox(height: FwLayout.s3),
      Text(
        'Open page: ${_session?['open_origin'] ?? 'none'}. '
        '${cap == null ? 'No session cap.' : 'Session cap $cap.'} '
        '${refuseKinds.isEmpty ? 'No kind of act is refused outright.' : ''}',
        style: TextStyle(fontSize: 12.5, color: t.inkMuted),
      ),
    ]);
  }

  Widget _verdicts(BuildContext context) {
    final t = context.fw;
    final all = ((_session?['actions'] as List?) ?? const [])
        .whereType<Map>()
        .map((m) => m.map((k, v) => MapEntry(k.toString(), v)))
        .toList();
    if (all.isEmpty) {
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Kicker('Verdicts'),
        const SizedBox(height: FwLayout.s2),
        Text('Nothing has been attempted.',
            style: TextStyle(fontSize: 12.5, color: t.ink)),
      ]);
    }
    final shown = all.take(_actionsShown).toList();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('Verdicts'),
      const SizedBox(height: FwLayout.s2),
      for (final act in shown) ...[
        _verdict(act, t),
        const SizedBox(height: FwLayout.s2),
      ],
      if (all.length > shown.length)
        HonestNull('${all.length - shown.length} further act(s) are counted '
            'above and not drawn here.'),
    ]);
  }

  Widget _verdict(Map<String, dynamic> act, FwTokens t) {
    final admitted = act['admitted'] == true;
    final inner = _asMap(act['action']) ?? const {};
    final target = inner['url'] ?? inner['selector'] ?? inner['field'] ?? '';
    return Row(children: [
      VerdictDot(admitted ? 'verified' : 'drift'),
      const SizedBox(width: FwLayout.s2),
      Text('${inner['kind'] ?? ''}',
          style: TextStyle(fontSize: 12, color: t.ink)),
      const SizedBox(width: FwLayout.s2),
      Expanded(
        child: Text('$target',
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 12, color: t.inkMuted)),
      ),
      const SizedBox(width: FwLayout.s3),
      Text(admitted ? (act['performed'] == true ? 'performed' : 'recorded')
          : '${act['reason'] ?? 'refused'}',
          style: TextStyle(fontSize: 12, color: t.inkMuted)),
    ]);
  }
}

int _int(Object? value) => value is num ? value.toInt() : 0;

Map<String, dynamic>? _asMap(Object? value) => value is Map
    ? value.map((k, v) => MapEntry(k.toString(), v))
    : null;

List<String> _list(Object? value) => value is List
    ? value.map((v) => v.toString()).toList()
    : const <String>[];
