import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models/studio_media.dart';
import '../services/studio_audio_player.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class StudioAudioPlayer extends StatefulWidget {
  final StudioAudio audio;
  final StudioAudioPlayback? playback;

  const StudioAudioPlayer({super.key, required this.audio, this.playback});

  @override
  State<StudioAudioPlayer> createState() => _StudioAudioPlayerState();
}

class _StudioAudioPlayerState extends State<StudioAudioPlayer> {
  late StudioAudioPlayback _playback;
  late bool _ownsPlayback;

  @override
  void initState() {
    super.initState();
    _attachPlayback();
    unawaited(_playback.load(widget.audio));
  }

  @override
  void didUpdateWidget(StudioAudioPlayer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.playback != widget.playback) {
      if (_ownsPlayback) unawaited(_playback.close());
      _attachPlayback();
      unawaited(_playback.load(widget.audio));
      return;
    }
    if (oldWidget.audio.sha256Hex != widget.audio.sha256Hex) {
      unawaited(_playback.load(widget.audio));
    }
  }

  @override
  void dispose() {
    if (_ownsPlayback) {
      unawaited(_playback.close());
    } else {
      unawaited(_playback.clear());
    }
    super.dispose();
  }

  void _attachPlayback() {
    _ownsPlayback = widget.playback == null;
    _playback = widget.playback ?? StudioAudioPlaybackController();
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return AnimatedBuilder(
      animation: _playback,
      builder: (context, _) {
        final state = _playback.state;
        final audio = state.audio ?? widget.audio;
        final position = state.position;
        final duration = audio.duration;
        final maxMicros = math.max(1, duration.inMicroseconds).toDouble();
        final value = position.inMicroseconds.clamp(0, maxMicros).toDouble();
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(
              height: 72,
              child: CustomPaint(
                key: const ValueKey('studio-audio-waveform'),
                painter: _WaveformPainter(audio.peaks, t),
              ),
            ),
            const SizedBox(height: FwLayout.s2),
            Row(children: [
              FilledButton(
                onPressed: state.isPlaying
                    ? () => unawaited(_playback.pause())
                    : () => unawaited(_playback.play()),
                child: Text(state.isPlaying ? 'Pause' : 'Play'),
              ),
              const SizedBox(width: FwLayout.s2),
              OutlinedButton(
                onPressed: () => unawaited(_playback.stop()),
                child: const Text('Stop'),
              ),
              const SizedBox(width: FwLayout.s3),
              Text(_clock(position), style: fwMono(t, size: 11.5)),
              Expanded(
                child: Slider(
                  value: value,
                  min: 0,
                  max: maxMicros,
                  onChanged: (v) => unawaited(
                    _playback.seek(Duration(microseconds: v.round())),
                  ),
                ),
              ),
              Text(_clock(duration), style: fwMono(t, size: 11.5)),
            ]),
            if (state.error != null) ...[
              const SizedBox(height: FwLayout.s2),
              HonestNull(state.error!),
            ],
          ],
        );
      },
    );
  }
}

class _WaveformPainter extends CustomPainter {
  _WaveformPainter(this.peaks, this.tokens);

  final List<double> peaks;
  final FwTokens tokens;

  @override
  void paint(Canvas canvas, Size size) {
    final axis = size.height / 2;
    final paint = Paint()
      ..color = tokens.inkMuted.withValues(alpha: 0.82)
      ..strokeCap = StrokeCap.round
      ..strokeWidth = math.max(1, size.width / math.max(1, peaks.length) * .45);
    final step = size.width / math.max(1, peaks.length);
    for (var i = 0; i < peaks.length; i++) {
      final x = step * (i + .5);
      final height = math.max(2, peaks[i] * size.height * .86);
      canvas.drawLine(
        Offset(x, axis - height / 2),
        Offset(x, axis + height / 2),
        paint,
      );
    }
    canvas.drawLine(
      Offset.zero.translate(0, axis),
      Offset(size.width, axis),
      Paint()
        ..color = tokens.line
        ..strokeWidth = 1,
    );
  }

  @override
  bool shouldRepaint(covariant _WaveformPainter oldDelegate) =>
      oldDelegate.peaks != peaks || oldDelegate.tokens != tokens;
}

String _clock(Duration value) {
  final minutes = value.inMinutes;
  final seconds = value.inSeconds.remainder(60).toString().padLeft(2, '0');
  return '$minutes:$seconds';
}
