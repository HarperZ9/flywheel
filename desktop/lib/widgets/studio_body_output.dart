import 'package:flutter/material.dart';

import '../models/studio_body_protocol.dart';
import '../models/studio_body_step.dart';
import '../models/studio_media.dart';
import 'fw.dart';
import 'studio_audio_player.dart';

/// Displays only bytes returned by a verified action, never illustrative data.
class StudioBodyOutput extends StatefulWidget {
  final StudioBodyStepResult result;
  const StudioBodyOutput({super.key, required this.result});

  @override
  State<StudioBodyOutput> createState() => _StudioBodyOutputState();
}

class _StudioBodyOutputState extends State<StudioBodyOutput> {
  StudioAudio? _audio;
  StudioFrame? _frame;
  List<StudioFrame> _frames = const [];
  int _index = 0;
  String? _error;

  @override
  void initState() {
    super.initState();
    _read();
  }

  @override
  void didUpdateWidget(covariant StudioBodyOutput oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.result, widget.result)) _read();
  }

  void _read() {
    _audio = null;
    _frame = null;
    _frames = const [];
    _index = 0;
    _error = null;
    if (!widget.result.verifiedDelivery) return;
    try {
      final result = widget.result;
      if (result.actionKind == studioBodySoundActionKind) {
        _audio = StudioAudio.fromResult(result.receipt);
      } else if (result.actionKind == studioBodyEngineActionKind) {
        final frames = result.receipt['frames'];
        if (frames is! List ||
            frames.isEmpty ||
            frames.length > 120 ||
            result.receipt['frame_count'] != frames.length) {
          throw const FormatException('No complete rendered frame set.');
        }
        var encodedBytes = 0;
        final checked = <StudioFrame>[];
        for (final raw in frames) {
          if (raw is! Map<String, dynamic> || raw['png_base64'] is! String) {
            throw const FormatException('Invalid rendered frame.');
          }
          encodedBytes += (raw['png_base64'] as String).length;
          if (encodedBytes > 64 * 1024 * 1024) {
            throw const FormatException('Frame set exceeds preview limits.');
          }
          checked.add(StudioFrame.fromJson(raw));
        }
        _frames = List.unmodifiable(checked);
        _readFrame();
      } else {
        throw const FormatException('This instrument has no media preview.');
      }
    } on FormatException catch (e) {
      _error = e.message;
    }
  }

  void _readFrame() {
    _frame = null;
    _error = null;
    _frame = _frames[_index];
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.result.verifiedDelivery) {
      return const HonestNull(
          'No verified output was produced by this action.');
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('instrument output'),
      const SizedBox(height: FwLayout.s2),
      if (_audio != null) StudioAudioPlayer(audio: _audio!),
      if (_error != null) HonestNull('Output unavailable: $_error'),
      if (_frame != null) ...[
        SizedBox(
          height: 300,
          width: double.infinity,
          child: Image.memory(
            _frame!.bytes,
            key: ValueKey('${_frame!.sha256Hex}:$_index'),
            fit: BoxFit.contain,
            semanticLabel: 'Rendered instrument frame ${_index + 1}',
            errorBuilder: (_, error, stack) => const HonestNull(
                'The frame hash matched, but the image could not be decoded.'),
          ),
        ),
        HashText('frame', _frame!.sha256Hex, keep: 16),
      ],
      if (_frames.isNotEmpty)
        Wrap(
          crossAxisAlignment: WrapCrossAlignment.center,
          spacing: FwLayout.s2,
          children: [
            IconButton(
              tooltip: 'Previous frame',
              onPressed: _index == 0
                  ? null
                  : () => setState(() {
                        _index--;
                        _readFrame();
                      }),
              icon: const Icon(Icons.chevron_left),
            ),
            Text('Frame ${_index + 1} of ${_frames.length}'),
            IconButton(
              tooltip: 'Next frame',
              onPressed: _index == _frames.length - 1
                  ? null
                  : () => setState(() {
                        _index++;
                        _readFrame();
                      }),
              icon: const Icon(Icons.chevron_right),
            ),
          ],
        ),
      const SizedBox(height: FwLayout.s2),
      const Text('Hashes check the returned bytes. They do not establish the '
          'quality of the output or that a model perceived it.'),
    ]);
  }
}
