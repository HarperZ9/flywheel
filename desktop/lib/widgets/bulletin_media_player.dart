import 'dart:io';

import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

final class BulletinMediaPlayer extends StatefulWidget {
  final File file;
  final String kind;
  const BulletinMediaPlayer({
    super.key,
    required this.file,
    required this.kind,
  });

  @override
  State<BulletinMediaPlayer> createState() => _BulletinMediaPlayerState();
}

final class _BulletinMediaPlayerState extends State<BulletinMediaPlayer> {
  VideoPlayerController? _controller;
  Future<void>? _ready;

  @override
  void initState() {
    super.initState();
    final controller = VideoPlayerController.file(widget.file);
    _controller = controller;
    _ready = controller.initialize().then((_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  Future<void> _toggle() async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) return;
    if (controller.value.isPlaying) {
      await controller.pause();
    } else {
      await controller.play();
    }
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<void>(
        future: _ready,
        builder: (context, snapshot) {
          final controller = _controller;
          if (snapshot.hasError || controller?.value.hasError == true) {
            return const Text('Media preview failed or unsupported.');
          }
          if (snapshot.connectionState != ConnectionState.done ||
              controller == null) {
            return const Text('Loading native media preview...');
          }
          if (!controller.value.isInitialized) {
            return const Text('Media preview failed or unsupported.');
          }
          final video = widget.kind == 'video';
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (video)
                AspectRatio(
                  aspectRatio: controller.value.aspectRatio <= 0
                      ? 16 / 9
                      : controller.value.aspectRatio,
                  child: VideoPlayer(controller),
                ),
              TextButton.icon(
                onPressed: _toggle,
                icon: Icon(controller.value.isPlaying
                    ? Icons.pause_circle_outline
                    : Icons.play_circle_outline),
                label: Text(controller.value.isPlaying ? 'Pause' : 'Play'),
              ),
            ],
          );
        },
      );
}
