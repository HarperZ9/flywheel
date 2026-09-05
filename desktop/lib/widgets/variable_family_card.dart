// variable_family_card.dart — ship the minted family as ONE variable font.
// A static family is a folder of weights; this is a single .ttf with a wght
// axis that interpolates between them. The engine proves the interpolation
// (instancing at a master reproduces it exactly); here we mint it from the
// last face's params and save the file, receipt beside it.
//
// The engine also mints the line as static weights, one .ttf per named style.
// That route had no surface at all, so the operator could ship the variable
// font and not the folder of weights it interpolates. Both actions live here
// because they are the same family, minted from the same seed.

import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

/// The weights the mint would not ship, by style name.
///
/// Two shapes carry them. A family that shipped puts them inside its receipt;
/// a family that refused entirely has no receipt and puts them at the top
/// level. Reading only the first renders a partial family as a complete one,
/// which is the failure this is written against.
List<String> refusedStyles(Map<String, dynamic> r) {
  final rows = (r['receipt'] is Map ? r['receipt']['refused_instances'] : null) ??
      r['refused_instances'];
  if (rows is! List) return const [];
  return [
    for (final row in rows)
      if (row is Map) '${row['style'] ?? '?'}'
  ];
}

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

  // The static half. Separate fields on purpose: shipping one form must not
  // silently replace the other form's result on screen.
  bool _staticBusy = false;
  Map<String, dynamic>? _familyReceipt;
  String? _familyError, _familyDir;
  int _familySaved = 0;
  List<String> _familyRefused = const [];

  /// Where a shipped file lands. Downloads, or the home directory if the
  /// platform names neither.
  String get _home =>
      Platform.environment['USERPROFILE'] ??
      Platform.environment['HOME'] ??
      '.';

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

  Future<void> _shipStatic() async {
    final fp = widget.faceParams;
    if (fp == null || _staticBusy) return;
    setState(() {
      _staticBusy = true;
      _familyError = null;
      _familyDir = null;
      _familySaved = 0;
      _familyRefused = const [];
    });
    try {
      final seed = fp['seed'] is int ? fp['seed'] as int : 58;
      final params = {...fp}..remove('seed');
      final r = await widget.client.typefaceFamily(params, seed);
      if (!mounted) return;
      // Named whether or not the whole mint refused.
      final refused = refusedStyles(r);
      if (r['refused'] == true) {
        setState(() {
          _familyRefused = refused;
          _familyError = (r['refusals'] is List &&
                  (r['refusals'] as List).isNotEmpty)
              ? '${(r['refusals'] as List).first}'
              : 'refused';
        });
        return;
      }
      final id = '${r['receipt']?['family_id'] ?? seed}';
      final sep = Platform.pathSeparator;
      final dir = Directory('$_home${sep}Downloads${sep}ZentropyMint-$id');
      dir.createSync(recursive: true);
      var saved = 0;
      for (final row in (r['instances'] as List? ?? const [])) {
        if (row is! Map) continue;
        final b64 = '${row['ttf_b64'] ?? ''}';
        if (b64.isEmpty) continue;
        final style = '${row['style'] ?? saved}'.replaceAll(RegExp(r'[^\w-]'), '');
        File('${dir.path}$sep$style.ttf').writeAsBytesSync(base64Decode(b64));
        saved++;
      }
      setState(() {
        _familyReceipt = r['receipt'] as Map<String, dynamic>?;
        _familyDir = dir.path;
        _familySaved = saved;
        _familyRefused = refused;
      });
    } catch (e) {
      if (mounted) setState(() => _familyError = '$e');
    } finally {
      if (mounted) setState(() => _staticBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final rc = _receipt;
    final fc = _familyReceipt;
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
        const SizedBox(height: FwLayout.s3),
        Row(children: [
          FilledButton.tonal(
            onPressed:
                (widget.faceParams == null || _staticBusy) ? null : _shipStatic,
            child: Text(_staticBusy ? 'Minting…' : 'Ship as static weights'),
          ),
          const SizedBox(width: FwLayout.s3),
          Flexible(
            child: Text(
                widget.faceParams == null
                    ? 'mint a face above first'
                    : 'one .ttf per named weight, in a folder of its own',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: fwMono(t, size: 10.5, color: t.inkFaint)),
          ),
        ]),
        if (_familyError != null) ...[
          const SizedBox(height: FwLayout.s2),
          HonestNull(_familyError!),
        ],
        // Refused weights show whether or not the mint as a whole refused. A
        // family missing two weights that reads as complete is the failure.
        if (_familyRefused.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          Text('refused: ${_familyRefused.join(', ')}',
              style: fwMono(t, size: 10.5, color: t.drift)),
        ],
        if (fc != null) ...[
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            VerdictPill('$_familySaved weights', status: 'verified'),
            const SizedBox(width: FwLayout.s2),
            if ('${fc['family_id'] ?? ''}'.isNotEmpty)
              HashText('family', '${fc['family_id']}', keep: 24),
          ]),
          if (_familyDir != null) ...[
            const SizedBox(height: FwLayout.s2),
            Text('saved $_familyDir',
                style: fwMono(t, size: 10.5, color: t.inkMuted),
                overflow: TextOverflow.ellipsis),
          ],
        ],
      ]),
    );
  }
}
