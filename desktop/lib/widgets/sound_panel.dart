// sound_panel.dart — the music station: a seeded chime study whose score
// IS the receipt. Compose, read the events, save the WAV; playback runs
// only after the receipt-bound WAV bytes validate.

import 'dart:io';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/studio_media.dart';
import '../services/studio_audio_player.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'studio_audio_player.dart';

class SoundPanel extends StatefulWidget {
  final GatewayClient client;
  final StudioAudioPlayback? playback;
  const SoundPanel({super.key, required this.client, this.playback});

  @override
  State<SoundPanel> createState() => _SoundPanelState();
}

class _SoundPanelState extends State<SoundPanel> {
  final _seed = TextEditingController(text: '58');
  double _duration = 24;
  double _root = 220;
  Map<String, dynamic>? _receipt;
  StudioAudio? _audio;
  bool _busy = false;
  String? _savedTo, _error;
  var _request = 0;

  @override
  void dispose() {
    _request++;
    _seed.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant SoundPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.client != widget.client) {
      _request++;
      setState(() {
        _audio = null;
        _receipt = null;
        _savedTo = null;
        _error = null;
      });
    }
  }

  Future<void> _compose() async {
    if (_busy) return;
    final request = ++_request;
    setState(() {
      _busy = true;
      _error = null;
      _savedTo = null;
      _audio = null;
      _receipt = null;
    });
    try {
      final r = await widget.client.studioSound(
        seed: int.tryParse(_seed.text.trim()) ?? 58,
        duration: _duration,
        root: _root,
      );
      if (!mounted || request != _request) return;
      setState(() {
        if (r['refused'] == true || r['error'] != null) {
          _error = (r['refusals'] is List && (r['refusals'] as List).isNotEmpty)
              ? '${(r['refusals'] as List).first}'
              : '${r['error'] ?? 'refused'}';
          _receipt = null;
        } else {
          final audio = StudioAudio.fromResult(r);
          _audio = audio;
          _receipt = r['receipt'] as Map<String, dynamic>?;
        }
      });
    } on FormatException catch (e) {
      if (mounted && request == _request) {
        setState(() => _error = e.message);
      }
    } catch (e) {
      if (mounted && request == _request) setState(() => _error = '$e');
    } finally {
      if (mounted && request == _request) setState(() => _busy = false);
    }
  }

  Future<void> _save() async {
    final audio = _audio;
    final rc = _receipt;
    if (audio == null || rc == null) return;
    try {
      final home = Platform.environment['USERPROFILE'] ??
          Platform.environment['HOME'] ??
          '.';
      final dir = Directory('$home${Platform.pathSeparator}Downloads');
      if (!dir.existsSync()) dir.createSync(recursive: true);
      final f = File('${dir.path}${Platform.pathSeparator}'
          'zentropy-study-${rc['seed']}.wav');
      f.writeAsBytesSync(audio.bytes);
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
              'rides the receipt. Same seed, same bytes. Playback starts '
              'only after the WAV matches its receipt.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          LayoutBuilder(builder: (context, box) {
            final narrow = box.maxWidth < 480;
            if (narrow) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(children: [
                    SizedBox(
                      width: 80,
                      child: TextField(
                        controller: _seed,
                        style: fwMono(t, size: 12),
                        decoration: const InputDecoration(hintText: 'seed'),
                      ),
                    ),
                    const Spacer(),
                    FilledButton(
                      onPressed: _busy ? null : _compose,
                      child: Text(_busy ? 'Composing…' : 'Compose'),
                    ),
                  ]),
                  const SizedBox(height: FwLayout.s2),
                  _sliderRow(t, 'duration', '${_duration.round()}s', _duration,
                      6, 60, (v) => _duration = v.roundToDouble()),
                  const SizedBox(height: FwLayout.s1),
                  _sliderRow(t, 'root', '${_root.round()}hz', _root, 110, 440,
                      (v) => _root = v.roundToDouble()),
                ],
              );
            }
            return Row(children: [
              SizedBox(
                width: 80,
                child: TextField(
                  controller: _seed,
                  style: fwMono(t, size: 12),
                  decoration: const InputDecoration(hintText: 'seed'),
                ),
              ),
              const SizedBox(width: FwLayout.s4),
              Text('duration',
                  style: fwMono(t, size: 11).copyWith(color: t.inkMuted)),
              Expanded(
                child: Slider(
                  value: _duration,
                  min: 6,
                  max: 60,
                  onChanged: (v) =>
                      setState(() => _duration = v.roundToDouble()),
                ),
              ),
              Text('${_duration.round()}s', style: fwMono(t, size: 11.5)),
              const SizedBox(width: FwLayout.s4),
              Text('root',
                  style: fwMono(t, size: 11).copyWith(color: t.inkMuted)),
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
            ]);
          }),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s2),
            HonestNull(_error!),
          ],
          if (_receipt != null) ...[
            const SizedBox(height: FwLayout.s3),
            if (_audio != null) ...[
              StudioAudioPlayer(
                audio: _audio!,
                playback: widget.playback,
              ),
              const SizedBox(height: FwLayout.s3),
            ],
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

  Widget _sliderRow(FwTokens t, String label, String display, double value,
      double min, double max, void Function(double) set) {
    return Row(children: [
      SizedBox(
        width: 64,
        child:
            Text(label, style: fwMono(t, size: 11).copyWith(color: t.inkMuted)),
      ),
      Expanded(
        child: Slider(
          value: value,
          min: min,
          max: max,
          onChanged: (v) => setState(() => set(v)),
        ),
      ),
      Text(display, style: fwMono(t, size: 11.5)),
    ]);
  }
}
