// sound_panel.dart — the music station: a seeded chime study whose score
// IS the receipt. Compose, read the events, save the WAV; playback runs
// through your system player, honestly stated rather than half-built.

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class SoundPanel extends StatefulWidget {
  final GatewayClient client;
  const SoundPanel({super.key, required this.client});

  @override
  State<SoundPanel> createState() => _SoundPanelState();
}

class _SoundPanelState extends State<SoundPanel> {
  final _seed = TextEditingController(text: '58');
  double _duration = 24;
  double _root = 220;
  Map<String, dynamic>? _receipt;
  Uint8List? _wav;
  bool _busy = false;
  String? _savedTo, _error;

  @override
  void dispose() {
    _seed.dispose();
    super.dispose();
  }

  Future<void> _compose() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _savedTo = null;
    });
    try {
      final r = await widget.client.studioSound(
        seed: int.tryParse(_seed.text.trim()) ?? 58,
        duration: _duration,
        root: _root,
      );
      if (!mounted) return;
      setState(() {
        if (r['refused'] == true || r['error'] != null) {
          _error = (r['refusals'] is List && (r['refusals'] as List).isNotEmpty)
              ? '${(r['refusals'] as List).first}'
              : '${r['error'] ?? 'refused'}';
          _wav = null;
          _receipt = null;
        } else {
          _wav = base64Decode('${r['wav_b64']}');
          _receipt = r['receipt'] as Map<String, dynamic>?;
        }
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _save() async {
    final wav = _wav;
    final rc = _receipt;
    if (wav == null || rc == null) return;
    try {
      final home = Platform.environment['USERPROFILE'] ??
          Platform.environment['HOME'] ??
          '.';
      final dir = Directory('$home${Platform.pathSeparator}Downloads');
      if (!dir.existsSync()) dir.createSync(recursive: true);
      final f = File('${dir.path}${Platform.pathSeparator}'
          'zentropy-study-${rc['seed']}.wav');
      f.writeAsBytesSync(wav);
      setState(() => _savedTo = f.path);
    } catch (e) {
      setState(() => _error = 'save failed: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
              'A seeded chime study: the same generator that lays out the '
              'plate places a pentatonic row over a drone, and the score '
              'rides the receipt. Same seed, same bytes. Playback is your '
              'system player\'s job; this station composes and proves.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            SizedBox(
              width: 80,
              child: TextField(
                controller: _seed,
                style: fwMono(t, size: 12),
                decoration: const InputDecoration(hintText: 'seed'),
              ),
            ),
            const SizedBox(width: FwLayout.s4),
            Text('duration', style: fwMono(t, size: 11).copyWith(color: t.inkMuted)),
            Expanded(
              child: Slider(
                value: _duration,
                min: 6,
                max: 60,
                onChanged: (v) => setState(() => _duration = v.roundToDouble()),
              ),
            ),
            Text('${_duration.round()}s', style: fwMono(t, size: 11.5)),
            const SizedBox(width: FwLayout.s4),
            Text('root', style: fwMono(t, size: 11).copyWith(color: t.inkMuted)),
            Expanded(
              child: Slider(
                value: _root,
                min: 110,
                max: 440,
                onChanged: (v) => setState(() => _root = v.roundToDouble()),
              ),
            ),
            Text('${_root.round()}hz', style: fwMono(t, size: 11.5)),
            const SizedBox(width: FwLayout.s3),
            FilledButton(
              onPressed: _busy ? null : _compose,
              child: Text(_busy ? 'Composing…' : 'Compose'),
            ),
          ]),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s2),
            HonestNull(_error!),
          ],
          if (_receipt != null) ...[
            const SizedBox(height: FwLayout.s3),
            Row(children: [
              VerdictPill('${_receipt!['n_events']} chimes',
                  status: 'verified'),
              const SizedBox(width: FwLayout.s2),
              Expanded(
                child: HashText('score', '${_receipt!['score_sha256'] ?? ''}',
                    keep: 16),
              ),
              Expanded(
                child: HashText('wav', '${_receipt!['wav_sha256'] ?? ''}',
                    keep: 16),
              ),
              OutlinedButton(onPressed: _save, child: const Text('Save WAV')),
            ]),
            if (_savedTo != null) ...[
              const SizedBox(height: FwLayout.s2),
              Row(children: [
                const VerdictPill('saved', status: 'verified'),
                const SizedBox(width: FwLayout.s2),
                Expanded(
                    child: Text(_savedTo!,
                        style: fwMono(t, size: 11).copyWith(color: t.inkMuted),
                        overflow: TextOverflow.ellipsis)),
              ]),
            ],
          ],
        ],
      ),
    );
  }
}
