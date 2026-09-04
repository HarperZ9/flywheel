// infra_view.dart -- the boundary the agent runs inside.
//
// Six surfaces over one question: what actually contains this thing. Three
// read the boundary as it stands, and three act on it. The three that act
// each pass through the grant sheet, because a credential scan reads where
// secrets live, an isolation probe leaves the machine, and the kill switch
// tries to stop a running agent. None of those is a plain button.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../client/gateway_infra.dart';
import '../widgets/fw.dart';
import '../widgets/infra_egress_panel.dart';
import '../widgets/infra_kill_panel.dart';
import '../widgets/infra_probe_panels.dart';
import '../widgets/infra_trust_panel.dart';

class InfraView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const InfraView({super.key, required this.client, required this.alive});

  @override
  State<InfraView> createState() => _InfraViewState();
}

class _InfraViewState extends State<InfraView> {
  Map<String, dynamic>? _trust;
  Map<String, dynamic>? _bom;
  Map<String, dynamic>? _egress;
  String? _error;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(InfraView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  Future<void> _load() async {
    if (!widget.alive || _loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      // Three independent reads, so they go out together rather than one
      // after another. The egress scan is the slow one.
      final results = await Future.wait([
        widget.client.infraTrustModel(),
        widget.client.infraBom(),
        widget.client.infraEgress(),
      ]);
      if (mounted) {
        setState(() {
          _trust = results[0];
          _bom = results[1];
          _egress = results[2];
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ViewScroll(
      storageKey: 'infra',
      children: [
        SectionHeader('Infrastructure',
            kicker: 'the boundary the agent runs inside',
            trailing: FilledButton.tonal(
              onPressed: _loading || !widget.alive ? null : _load,
              child: Text(_loading ? 'Reading…' : 'Re-read'),
            )),
        const SizedBox(height: FwLayout.s4),
        if (!widget.alive)
          const HonestNull('The gateway is not answering, so nothing here '
              'has been read. Nothing is claimed about the boundary.')
        else if (_error != null)
          HonestNull('The boundary could not be read: $_error'),
        const SizedBox(height: FwLayout.s4),
        TrustModelPanel(model: _trust),
        const SizedBox(height: FwLayout.s4),
        RunBomPanel(bom: _bom),
        const SizedBox(height: FwLayout.s4),
        EgressPanel(egress: _egress),
        const SizedBox(height: FwLayout.s6),
        const Kicker('acting on the boundary · each one is granted'),
        const SizedBox(height: FwLayout.s3),
        CredentialScanPanel(client: widget.client),
        const SizedBox(height: FwLayout.s4),
        IsolationProbePanel(client: widget.client),
        const SizedBox(height: FwLayout.s4),
        KillSwitchPanel(client: widget.client),
      ],
    );
  }
}
