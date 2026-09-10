import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import '../assistant/assistant_identity.dart';
import '../theme/flywheel_theme.dart';
import 'rowan_shader.dart';
import 'rowan_visibility.dart';

/// One modeled Rowan identity. Small UI avatars are static by default.
class RowanAvatar extends StatefulWidget {
  const RowanAvatar(
      {super.key,
      this.size = 32,
      this.animated = false,
      this.pose = const RowanPose(),
      this.loadProgram,
      this.onRendererReady})
      : assert(size > 0 && size <= 1024);
  final double size;
  final bool animated;
  final RowanPose pose;
  final Future<ui.FragmentProgram> Function()? loadProgram;
  final ValueChanged<bool>? onRendererReady;

  @override
  State<RowanAvatar> createState() => _RowanAvatarState();
}

class _RowanAvatarState extends State<RowanAvatar>
    with SingleTickerProviderStateMixin, WidgetsBindingObserver {
  final _time = ValueNotifier<double>(0);
  late final Ticker _ticker;
  ui.FragmentShader? _shader;
  bool _failed = false;
  bool _active = true;
  bool _motionAllowed = false;
  bool _playing = false;
  bool _scheduled = false;
  int _loadEpoch = 0;
  Duration? _lastTick;
  final _scrollPositions = <ScrollPosition>{};

  @override
  void initState() {
    super.initState();
    _ticker = createTicker(_tick);
    WidgetsBinding.instance.addObserver(this);
    final state = WidgetsBinding.instance.lifecycleState;
    _active = state == null || state == AppLifecycleState.resumed;
    _load();
  }

  void _load() {
    final epoch = ++_loadEpoch;
    _shader?.dispose();
    _shader = null;
    _failed = false;
    (widget.loadProgram ?? RowanShader.load)().then((program) {
      if (!mounted || epoch != _loadEpoch) return;
      setState(() => _shader = program.fragmentShader());
      widget.onRendererReady?.call(true);
      _scheduleMotion();
    }).catchError((Object error) {
      if (!mounted || epoch != _loadEpoch) return;
      setState(() => _failed = true);
      widget.onRendererReady?.call(false);
      _updateMotion();
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _motionAllowed = !MediaQuery.disableAnimationsOf(context) &&
        TickerMode.valuesOf(context).enabled;
    final positions = <ScrollPosition>{};
    var scrollable = Scrollable.maybeOf(context);
    while (scrollable != null && positions.add(scrollable.position)) {
      scrollable = Scrollable.maybeOf(scrollable.context);
    }
    for (final position in _scrollPositions.difference(positions)) {
      position.removeListener(_scheduleMotion);
    }
    for (final position in positions.difference(_scrollPositions)) {
      position.addListener(_scheduleMotion);
    }
    _scrollPositions
      ..clear()
      ..addAll(positions);
    _scheduleMotion();
  }

  @override
  void didUpdateWidget(RowanAvatar oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.loadProgram != widget.loadProgram) _load();
    _scheduleMotion();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _active = state == AppLifecycleState.resumed;
    if (!_active) {
      _updateMotion();
    } else {
      _scheduleMotion();
      WidgetsBinding.instance.ensureVisualUpdate();
    }
  }

  void _scheduleMotion() {
    if (!mounted || _scheduled) return;
    _scheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scheduled = false;
      if (mounted) _updateMotion();
    });
  }

  void _updateMotion() {
    final play = widget.animated &&
        _motionAllowed &&
        _active &&
        _shader != null &&
        rowanIsVisible(context);
    if (play == _playing) return;
    setState(() => _playing = play);
    _lastTick = null;
    if (play) {
      _ticker.start();
    } else {
      _ticker.stop();
    }
  }

  void _tick(Duration elapsed) {
    if (!rowanIsVisible(context)) {
      _updateMotion();
      return;
    }
    final last = _lastTick;
    _lastTick = elapsed;
    if (last != null) _time.value += (elapsed - last).inMicroseconds / 1000000;
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    for (final position in _scrollPositions) {
      position.removeListener(_scheduleMotion);
    }
    _ticker.dispose();
    _shader?.dispose();
    _time.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final shader = _shader;
    final label = _failed
        ? '${AssistantIdentity.name}, simple fallback drawing'
        : shader == null
            ? '${AssistantIdentity.name}, loading modeled renderer'
            : AssistantIdentity.name;
    return Semantics(
        label: label,
        image: true,
        child: Tooltip(
            message: label,
            excludeFromSemantics: true,
            child: ExcludeSemantics(
              child: RowanPaintObserver(
                onPaint: () {
                  if (widget.animated) _scheduleMotion();
                },
                child: RepaintBoundary(
                    child: SizedBox.square(
                        dimension: widget.size,
                        child: CustomPaint(
                          painter: shader == null
                              ? RowanFallbackPainter(context.fw.inkMuted)
                              : RowanShaderPainter(
                                  shader: shader,
                                  time: _time,
                                  motion: _playing,
                                  pose: widget.pose),
                        ))),
              ),
            )));
  }
}
