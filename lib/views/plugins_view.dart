// plugins_view.dart — the Plugins view: every capability the surface
// mounts, one manifest shape. Bundled lanes and the gated builtin tool set
// are always present; custom MCP servers register by command. Probing
// spawns the server and shows its real tools; registration grants nothing.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import '../widgets/parity_table.dart';

class PluginsView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const PluginsView({super.key, required this.client, required this.alive});

  @override
  State<PluginsView> createState() => _PluginsViewState();
}

class _PluginsViewState extends State<PluginsView> {
  final _name = TextEditingController();
  final _command = TextEditingController();
  List<Map<String, dynamic>> _plugins = [];
  final Map<String, Map<String, dynamic>> _probes = {};
  final Set<String> _probing = {};
  Map<String, dynamic>? _parity;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(PluginsView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  @override
  void dispose() {
    _name.dispose();
    _command.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (!widget.alive) return;
    try {
      final results =
          await Future.wait([widget.client.plugins(), widget.client.parity()]);
      if (mounted) {
        setState(() {
          _plugins = ((results[0]['plugins'] ?? []) as List)
              .whereType<Map<String, dynamic>>()
              .toList();
          _parity = results[1];
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _probe(String name) async {
    setState(() => _probing.add(name));
    try {
      final r = await widget.client.probePlugin(name);
      if (mounted) setState(() => _probes[name] = r);
    } catch (e) {
      if (mounted) setState(() => _probes[name] = {'status': 'error', 'detail': '$e'});
    } finally {
      if (mounted) setState(() => _probing.remove(name));
    }
  }

  Future<void> _register() async {
    final name = _name.text.trim();
    final argv = _command.text.trim().split(RegExp(r'\s+'));
    if (name.isEmpty || argv.isEmpty || argv.first.isEmpty) return;
    try {
      final r = await widget.client.registerPlugin(name, argv);
      if (r['error'] != null) {
        setState(() => _error = '${r['error']}');
      } else {
        _name.clear();
        _command.clear();
        _error = null;
        _load();
      }
    } catch (e) {
      setState(() => _error = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. Plugins appear when it runs.',
          command: 'flywheel up');
    }
    return ViewScroll(
      children: [
        const SectionHeader('Plugins', kicker: 'one manifest, every capability'),
        const SizedBox(height: FwLayout.s3),
        Text(
          'Lanes, the gated builtin tool set, and your own MCP servers mount '
          'through one registry. Registering grants nothing: outbound calls '
          'stay behind the tool gate, and probing shows the server\'s own '
          'answer, never an assumption.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull(_error!),
        ],
        const SizedBox(height: FwLayout.s4),
        for (final p in _plugins) _pluginCard(context, p),
        const SizedBox(height: FwLayout.s4),
        const Kicker('register an mcp server', hot: true),
        const SizedBox(height: FwLayout.s3),
        _registerForm(context),
        if (_parity != null) ...[
          const SizedBox(height: FwLayout.s5),
          const Kicker('parity · audited here, declared there'),
          const SizedBox(height: FwLayout.s3),
          ParityTable(doc: _parity!),
        ],
      ],
    );
  }

  Widget _pluginCard(BuildContext context, Map<String, dynamic> p) {
    final t = context.fw;
    final name = '${p['name']}';
    final kind = '${p['kind']}';
    final enabled = p['enabled'] == true;
    final probe = _probes[name];
    return Padding(
      padding: const EdgeInsets.only(bottom: FwLayout.s3),
      child: HairlineCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(name,
                      style: const TextStyle(
                          fontSize: 14.5, fontWeight: FontWeight.w700)),
                ),
                VerdictPill(kind, status: 'unverifiable'),
                const SizedBox(width: FwLayout.s2),
                VerdictPill(enabled ? 'enabled' : 'disabled',
                    status: enabled ? 'verified' : 'absent'),
              ],
            ),
            const SizedBox(height: FwLayout.s2),
            Text('${p['detail'] ?? ''}',
                style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
            const SizedBox(height: FwLayout.s3),
            Row(
              children: [
                OutlinedButton(
                  onPressed:
                      _probing.contains(name) ? null : () => _probe(name),
                  child:
                      Text(_probing.contains(name) ? 'Probing…' : 'Probe'),
                ),
                const SizedBox(width: FwLayout.s3),
                if (p['removable'] == true) ...[
                  OutlinedButton(
                    onPressed: () async {
                      await widget.client.togglePlugin(name, !enabled);
                      _load();
                    },
                    child: Text(enabled ? 'Disable' : 'Enable'),
                  ),
                  const SizedBox(width: FwLayout.s3),
                  OutlinedButton(
                    onPressed: () async {
                      await widget.client.removePlugin(name);
                      _probes.remove(name);
                      _load();
                    },
                    child: const Text('Remove'),
                  ),
                ],
              ],
            ),
            if (probe != null) ...[
              const SizedBox(height: FwLayout.s3),
              _probeResult(t, probe),
            ],
          ],
        ),
      ),
    );
  }

  Widget _probeResult(FwTokens t, Map<String, dynamic> probe) {
    final status = '${probe['status'] ?? probe['error'] ?? '?'}';
    final tools = (probe['tools'] is List)
        ? List<String>.from(probe['tools'])
        : const <String>[];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            VerdictPill(status,
                status: status == 'live' ? 'verified' : 'drift'),
            if ('${probe['detail'] ?? ''}'.isNotEmpty) ...[
              const SizedBox(width: FwLayout.s2),
              Expanded(
                child: Text('${probe['detail']}',
                    overflow: TextOverflow.ellipsis,
                    style: fwMono(t, size: 10.5, color: t.inkFaint)),
              ),
            ],
          ],
        ),
        if (tools.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          Wrap(
            spacing: 4,
            runSpacing: 4,
            children: [
              for (final tool in tools)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: t.ground2,
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: t.hairline),
                  ),
                  child: Text(tool, style: fwMono(t, size: 10)),
                ),
            ],
          ),
        ],
      ],
    );
  }

  Widget _registerForm(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              SizedBox(
                width: 160,
                child: TextField(
                  controller: _name,
                  style: fwMono(t, size: 12.5),
                  decoration: const InputDecoration(hintText: 'name'),
                ),
              ),
              const SizedBox(width: FwLayout.s3),
              Expanded(
                child: TextField(
                  controller: _command,
                  style: fwMono(t, size: 12.5),
                  decoration: const InputDecoration(
                      hintText: 'command, e.g. gather mcp'),
                  onSubmitted: (_) => _register(),
                ),
              ),
              const SizedBox(width: FwLayout.s3),
              FilledButton(onPressed: _register, child: const Text('Register')),
            ],
          ),
          const SizedBox(height: FwLayout.s2),
          Text(
              'The command is the argv that starts the server over stdio. '
              'It runs only when probed or when a gated run allows MCP.',
              style: TextStyle(fontSize: 11.5, color: t.inkFaint)),
        ],
      ),
    );
  }
}
