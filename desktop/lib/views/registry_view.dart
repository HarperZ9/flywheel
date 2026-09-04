// registry_view.dart - what the engine registers, and what it believes.
//
// Six read-only gateway routes that the app had never called: the credo, the
// loop register, the hook / skill / pack registries, and credential handle
// presence. All reads. Nothing here mutates anything.
//
// An empty registry reads as empty. That is a true state of a fresh install,
// and dressing it as "loading" or hiding the section would make a working
// engine look broken.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../client/gateway_registry.dart';
import '../models/registry_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import '../widgets/pack_admit_panel.dart';

class RegistryView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const RegistryView({super.key, required this.client, required this.alive});

  @override
  State<RegistryView> createState() => _RegistryViewState();
}

class _RegistryViewState extends State<RegistryView> {
  Credo? _credo;
  LoopRegister? _loops;
  NamedRegistry? _hooks;
  NamedRegistry? _skills;
  NamedRegistry? _packs;
  CredentialHandles? _handles;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    if (widget.alive) _load();
  }

  @override
  void didUpdateWidget(RegistryView old) {
    super.didUpdateWidget(old);
    if (widget.alive && !old.alive) _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final r = await Future.wait([
        widget.client.credo(),
        widget.client.loops(),
        widget.client.hooks(),
        widget.client.skills(),
        widget.client.packs(),
        widget.client.credentialHandles(),
      ]);
      if (!mounted) return;
      setState(() {
        _credo = Credo.fromJson(r[0]);
        _loops = LoopRegister.fromJson(r[1]);
        _hooks = NamedRegistry.fromJson(r[2], 'hooks');
        _skills = NamedRegistry.fromJson(r[3], 'skills');
        _packs = NamedRegistry.fromJson(r[4], 'packs');
        _handles = CredentialHandles.fromJson(r[5]);
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = '$e';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. Registries appear when it runs.',
          command: 'flywheel up');
    }
    return ViewScroll(
      children: [
        SectionHeader(
          'Registry',
          kicker: 'what the engine registers, and what it believes',
          trailing: IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh, size: 18),
            onPressed: _loading ? null : _load,
          ),
        ),
        if (_loading) ...[
          const SizedBox(height: FwLayout.s2),
          const LinearProgressIndicator(minHeight: 2),
        ],
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s2),
          HonestNull('The registries could not be read: $_error'),
        ],
        if (_loops != null) ...[
          const SizedBox(height: FwLayout.s3),
          _loopsCard(t, _loops!),
        ],
        const SizedBox(height: FwLayout.s3),
        AdaptiveTiles(children: [
          if (_hooks != null) _registryTile('hooks', _hooks!),
          if (_skills != null) _registryTile('skills', _skills!),
          if (_packs != null) _registryTile('packs', _packs!),
        ]),
        if (_handles != null) ...[
          const SizedBox(height: FwLayout.s3),
          _handlesCard(t, _handles!),
        ],
        if (_credo != null) ...[
          const SizedBox(height: FwLayout.s3),
          _credoCard(t, _credo!),
        ],
        const SizedBox(height: FwLayout.s5),
        PackAdmitPanel(client: widget.client),
      ],
    );
  }

  Widget _registryTile(String label, NamedRegistry r) {
    if (r.error != null) return StatTile(label: label, value: 'unreadable');
    return StatTile(
      label: label,
      value: '${r.count}',
      status: r.countDisagrees ? 'drift' : null,
    );
  }

  Widget _loopsCard(FwTokens t, LoopRegister r) {
    if (r.error != null) {
      return HonestNull('The loop register could not be read: ${r.error}');
    }
    if (r.loops.isEmpty) {
      return const HonestNull('No loop has been measured yet.');
    }
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('loops'),
          const SizedBox(height: FwLayout.s1),
          Text('${r.closedCount} of ${r.total} close. Measured from the edges '
              'each loop names, not asserted.',
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: t.inkMuted)),
          const SizedBox(height: FwLayout.s2),
          for (final loop in r.loops)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 84,
                    child: Text(loop.name,
                        style: fwMono(t, size: 11.5, color: t.ink)),
                  ),
                  SizedBox(
                    width: 60,
                    child: Text(loop.closed ? 'closed' : 'open',
                        style: fwMono(t,
                            size: 11,
                            color: loop.closed ? t.verified : t.unverifiable)),
                  ),
                  Expanded(
                    child: Text(loop.question,
                        style: Theme.of(context)
                            .textTheme
                            .bodySmall
                            ?.copyWith(color: t.inkMuted)),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _handlesCard(FwTokens t, CredentialHandles h) {
    if (h.error != null) {
      return HonestNull('Credential handles could not be read: ${h.error}');
    }
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('credential handles'),
          const SizedBox(height: FwLayout.s1),
          Text(
              h.handles.isEmpty
                  ? 'No handle is bound.'
                  : '${h.handles.length} bound: ${h.handles.join(', ')}',
              style: fwMono(t, size: 11.5, color: t.inkSoft)),
          const SizedBox(height: FwLayout.s1),
          Text('Presence only. A handle names a credential; the value never '
              'leaves the engine and this app never asks for one.',
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: t.inkFaint)),
        ],
      ),
    );
  }

  Widget _credoCard(FwTokens t, Credo c) {
    if (c.error != null) {
      return HonestNull('The credo could not be read: ${c.error}');
    }
    if (c.text.isEmpty) return const SizedBox.shrink();
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('credo'),
          const SizedBox(height: FwLayout.s1),
          Text(c.text, style: Theme.of(context).textTheme.bodySmall),
          if (c.sha256.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s2),
            HashText('sha256', c.sha256),
          ],
        ],
      ),
    );
  }
}
