import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import '../assistant/assistant_identity.dart';
import 'fw.dart';
import 'rowan_avatar.dart';
import 'rowan_shader.dart';

class RowanPresenter extends StatefulWidget {
  const RowanPresenter({super.key, this.loadProgram});
  final Future<ui.FragmentProgram> Function()? loadProgram;
  @override
  State<RowanPresenter> createState() => _RowanPresenterState();
}

class _RowanPresenterState extends State<RowanPresenter> {
  final _turnFocus = FocusNode(debugLabel: 'Turn Rowan');
  bool _motion = false;
  bool _ready = false;
  bool _failed = false;
  double _yaw = 0;
  Offset _gaze = Offset.zero;

  @override
  void didUpdateWidget(RowanPresenter oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.loadProgram != widget.loadProgram) {
      _ready = false;
      _failed = false;
    }
  }

  @override
  void dispose() {
    _turnFocus.dispose();
    super.dispose();
  }

  void _availability(bool ready) {
    if (mounted) {
      setState(() {
        _ready = ready;
        _failed = !ready;
      });
    }
  }

  @override
  Widget build(BuildContext context) => HairlineCard(
          child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker(AssistantIdentity.name),
          const SizedBox(height: FwLayout.s2),
          Text(_failed
              ? 'Modeled renderer unavailable. Showing a simple drawing.'
              : !_ready
                  ? 'Loading the modeled renderer. Controls will be available when ready.'
                  : 'Turn Rowan or move the pointer to adjust the gaze. Motion is optional.'),
          const SizedBox(height: FwLayout.s3),
          Center(child: LayoutBuilder(builder: (context, constraints) {
            final size = constraints.maxWidth.clamp(1.0, 320.0);
            return MouseRegion(
              onHover: !_ready
                  ? null
                  : (event) => setState(() => _gaze = Offset(
                      event.localPosition.dx / size * 2 - 1,
                      event.localPosition.dy / size * 2 - 1)),
              onExit: (_) => setState(() => _gaze = Offset.zero),
              child: RowanAvatar(
                  loadProgram: widget.loadProgram,
                  size: size,
                  animated: _motion,
                  pose: RowanPose(gaze: _gaze, yaw: _yaw),
                  onRendererReady: _availability),
            );
          })),
          const SizedBox(height: FwLayout.s2),
          Row(children: [
            const Text('Turn'),
            Expanded(
                child: Semantics(
                    label: 'Turn Rowan',
                    child: Slider(
                        focusNode: _turnFocus,
                        value: _yaw,
                        min: -.6,
                        max: .6,
                        semanticFormatterCallback: (value) =>
                            '${(value * 180 / 3.141592653589793).round()} degrees',
                        onChanged: !_ready
                            ? null
                            : (value) => setState(() => _yaw = value)))),
          ]),
          Material(
              type: MaterialType.transparency,
              child: SwitchListTile.adaptive(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Motion'),
                  subtitle: const Text(
                      'Pauses when hidden, inactive, or reduced motion is enabled.'),
                  value: _motion,
                  onChanged: !_ready
                      ? null
                      : (value) => setState(() => _motion = value))),
        ],
      ));
}
