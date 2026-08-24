// rail_resizer.dart -- the drag handle on the rail's right edge.
// A drag-only control is unreachable by keyboard, so the handle is also
// focusable and adjustable: Left and Right narrow or widen the rail in
// steps, Home and End jump to the bounds, and the semantics announce it.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class RailResizer extends StatefulWidget {
  final double width;
  final ValueChanged<double> onResize;
  final double min;
  final double max;

  const RailResizer({
    super.key,
    required this.width,
    required this.onResize,
    this.min = 148,
    this.max = 320,
  });

  @override
  State<RailResizer> createState() => _RailResizerState();
}

class _RailResizerState extends State<RailResizer> {
  late final FocusNode _node = FocusNode(onKeyEvent: _onKey)
    ..addListener(() {
      if (_focused != _node.hasFocus) setState(() => _focused = _node.hasFocus);
    });
  bool _focused = false;

  KeyEventResult _onKey(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent) return KeyEventResult.ignored;
    return switch (event.logicalKey) {
      LogicalKeyboardKey.arrowLeft => _apply(-16),
      LogicalKeyboardKey.arrowRight => _apply(16),
      LogicalKeyboardKey.home => _jump(widget.min),
      LogicalKeyboardKey.end => _jump(widget.max),
      _ => KeyEventResult.ignored,
    };
  }

  KeyEventResult _apply(double delta) {
    widget.onResize((widget.width + delta).clamp(widget.min, widget.max));
    return KeyEventResult.handled;
  }

  KeyEventResult _jump(double value) {
    widget.onResize(value.clamp(widget.min, widget.max));
    return KeyEventResult.handled;
  }

  @override
  void dispose() {
    _node.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Resize navigation rail',
      button: true,
      child: MouseRegion(
        cursor: SystemMouseCursors.resizeLeftRight,
        child: GestureDetector(
          behavior: HitTestBehavior.translucent,
          onHorizontalDragUpdate: (d) => widget
              .onResize((widget.width + d.delta.dx)
                  .clamp(widget.min, widget.max)),
          child: Focus(
            key: const Key('rail-resizer-focus'),
            focusNode: _node,
            child: DecoratedBox(
              decoration: BoxDecoration(
                border: _focused
                    ? Border.all(
                        color: Theme.of(context).colorScheme.primary,
                        width: 1)
                    : null,
              ),
              child: const SizedBox.expand(),
            ),
          ),
        ),
      ),
    );
  }
}
