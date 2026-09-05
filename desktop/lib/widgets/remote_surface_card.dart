// remote_surface_card.dart - the remote half of the relay card.
//
// Renders what relay reports about the phone-facing surface and nothing more.
// The half-configured case gets the hot mark: a surface serving the static
// bearer with an incomplete OAuth block looks configured from the outside and
// no phone will pair with it.

import 'package:flutter/material.dart';

import '../models/remote_surface.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class RemoteSurfaceCard extends StatelessWidget {
  final RemoteSurface surface;
  const RemoteSurfaceCard({super.key, required this.surface});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Remote access',
          style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
      const SizedBox(height: FwLayout.s2),
      switch (surface.reach) {
        RemoteReach.unknown => HonestNull(
            'Whether a phone can reach this workstation is unreported. '
            '${surface.reason}'),
        RemoteReach.off => HairlineCard(child: _off(context, t)),
        _ => HairlineCard(child: _on(context, t)),
      },
    ]);
  }

  Widget _off(BuildContext context, FwTokens t) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('off'),
      const SizedBox(height: FwLayout.s1),
      Text(surface.reason,
          style: TextStyle(color: t.inkSoft, fontSize: 12.5, height: 1.45)),
      const SizedBox(height: FwLayout.s2),
      _envLine(t),
    ]);
  }

  Widget _on(BuildContext context, FwTokens t) {
    final paired = surface.reach == RemoteReach.paired;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Kicker(paired ? 'paired' : 'bearer only'),
      const SizedBox(height: FwLayout.s1),
      Text(
          paired
              ? 'The remote surface is configured and a phone can pair with it.'
              : 'The remote surface serves the static bearer. The phone '
                  'connector needs every key below before it exists at all, '
                  'and the server does not say so when one is missing.',
          style: TextStyle(
              color: paired ? t.inkSoft : t.drift,
              fontSize: 12.5,
              height: 1.45)),
      if (!paired && surface.oauthMissing.isNotEmpty) ...[
        const SizedBox(height: FwLayout.s2),
        for (final key in surface.oauthMissing)
          Text('unset  $key', style: fwMono(t, size: 11.5, color: t.drift)),
      ],
      const SizedBox(height: FwLayout.s3),
      if (surface.publicUrl.isNotEmpty)
        _row(t, 'address', surface.publicUrl),
      if (surface.listen.isNotEmpty) _row(t, 'listens', surface.listen),
      _row(t, 'transport', surface.tlsConfigured ? 'TLS' : 'no TLS'),
      if (surface.remoteExecAllowed)
        _row(t, 'exec', 'remote execution allowed', hot: true),
      if (surface.allowedOrigins.isNotEmpty)
        _row(t, 'origins', surface.allowedOrigins.join('  ')),
      const SizedBox(height: FwLayout.s2),
      _envLine(t),
    ]);
  }

  Widget _row(FwTokens t, String label, String value, {bool hot = false}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 3),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
            width: 72,
            child: Text(label, style: fwMono(t, size: 11, color: t.inkFaint))),
        Expanded(
            child: SelectableText(value,
                style: fwMono(t, size: 11.5, color: hot ? t.drift : t.ink))),
      ]),
    );
  }

  /// Which file relay read, and whether it was there. An operator whose setup
  /// works and reads as off is usually looking at the wrong file.
  Widget _envLine(FwTokens t) {
    if (surface.envFile.isEmpty) return const SizedBox.shrink();
    final found = surface.envFileFound ? 'read' : 'not found';
    return Text('config  ${surface.envFile}  ($found)',
        style: fwMono(t, size: 11, color: t.inkFaint));
  }
}
