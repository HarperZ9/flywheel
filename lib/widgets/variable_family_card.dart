// variable_family_card.dart — ship the minted family as ONE variable font.
// A static family is a folder of weights; this is a single .ttf with a wght
// axis that interpolates between them. The engine proves the interpolation
// (instancing at a master reproduces it exactly); here we mint it from the
// last face's params and save the file, receipt beside it.

import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class VariableFamilyCard extends StatefulWidget {
  final GatewayClient client;

  /// The last minted face's params (incl. 'seed'); null until a face exists.
  final Map<String, dynamic>? faceParams;
  const VariableFamilyCard({super.key, required this.client, this.faceParams});

  @override
  State<VariableFamilyCard> createState() => _VariableFamilyCardState();
}

class _VariableFamilyCardState extends State<VariableFamilyCard> {
  bool _busy = false;
  Map<String, dynamic>? _receipt;
  String? _error, _savedTo;

  Future<void> _ship() async {
    final fp = widget.faceParams;
    if (fp == null || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _savedTo = null;
    });
    try {
      final seed = fp['seed'] is int ? fp['seed'] as int : 58;
      final params = {...fp}..remove('seed');
      final r = await widget.client.typefaceVariable(params, seed);
      if (!mounted) return;
      if (r['refused'] == true) {
        setState(() => _error = (r['refusals'] is List &&
                (r['refusals'] as List).isNotEmpty)
            ? '${(r['refusals'] as List).first}'
            : 'refused');
        return;
      }
      final ttf = base64Decode('${r['ttf_b64']}');
      final home = Platform.environment['USERPROFILE'] ??
          Platform.environment['HOME'] ??
          '.';
      final id = '${r['receipt']?['variable_id'] ?? seed}';
      final f = File('$home${Platform.pathSeparator}Downloads'
          '${Platform.pathSeparator}ZentropyMint-VF-$id.ttf');
      f.writeAsBytesSync(ttf);
      setState(() {
        _receipt = r['receipt'] as Map<String, dynamic>?;
        _savedTo = f.path;
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final rc = _receipt;
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          FilledButton.tonal(
            onPressed: (widget.faceParams == null || _busy) ? null : _ship,
            child: Text(_busy ? 'Minting…' : 'Ship as variable font'),
          ),
          const SizedBox(width: FwLayout.s3),
          Flexible(
            child: Text(
                widget.faceParams == null
                    ? 'mint a face above first'
                    : 'one .ttf, a wght axis interpolating the whole line',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: fwMono(t, size: 10.5, color: t.inkFaint)),
          ),
        ]),
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s2),
          HonestNull(_error!),
        ],
        if (rc != null) ...[
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            VerdictPill(
                '${(rc['masters'] as List?)?.length ?? 0} masters · wght',
                status: 'verified'),
            const SizedBox(width: FwLayout.s2),
            if ('${rc['variable_id'] ?? ''}'.isNotEmpty)
              HashText('variable', '${rc['variable_id']}', keep: 24),
          ]),
          if (_savedTo != null) ...[
            const SizedBox(height: FwLayout.s2),
            Text('saved $_savedTo',
                style: fwMono(t, size: 10.5, color: t.inkMuted),
                overflow: TextOverflow.ellipsis),
          ],
        ],
      ]),
    );
  }
}
