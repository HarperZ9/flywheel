// split_pane.dart — two panes with a draggable hairline divider. The chrome
// grammar for every resizable panel: 1px line inside a 9px grab strip, a
// resize cursor on hover, and hard minimum fractions so no pane can be
// dragged out of existence.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';

class SplitPane extends StatefulWidget {
  final Axis axis;
  final Widget first;
  final Widget second;
  final double initialFraction;
  final double minFraction;
  final double maxFraction;
  final ValueChanged<double>? onFraction;

  const SplitPane(
      {super.key,
      required this.axis,
      required this.first,
      required this.second,
      this.initialFraction = 0.3,
      this.minFraction = 0.1,
      this.maxFraction = 0.9,
      this.onFraction});

  @override
  State<SplitPane> createState() => _SplitPaneState();
}

class _SplitPaneState extends State<SplitPane> {
  static const _grip = 9.0;
  late double _fraction =
      widget.initialFraction.clamp(widget.minFraction, widget.maxFraction);

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final horizontal = widget.axis == Axis.horizontal;
    return LayoutBuilder(builder: (context, constraints) {
      final total =
          (horizontal ? constraints.maxWidth : constraints.maxHeight) - _grip;
      final firstExtent = (total * _fraction).clamp(0.0, total);
      void drag(DragUpdateDetails d) {
        final delta = horizontal ? d.delta.dx : d.delta.dy;
        setState(() {
          _fraction = ((firstExtent + delta) / total)
              .clamp(widget.minFraction, widget.maxFraction);
        });
        widget.onFraction?.call(_fraction);
      }

      final divider = MouseRegion(
        cursor: horizontal
            ? SystemMouseCursors.resizeColumn
            : SystemMouseCursors.resizeRow,
        child: GestureDetector(
          key: const Key('split-divider'),
          behavior: HitTestBehavior.opaque,
          onPanUpdate: drag,
          child: SizedBox(
            width: horizontal ? _grip : null,
            height: horizontal ? null : _grip,
            child: Center(
              child: Container(
                width: horizontal ? 1 : null,
                height: horizontal ? null : 1,
                color: t.line,
              ),
            ),
          ),
        ),
      );

      final children = [
        SizedBox(
          width: horizontal ? firstExtent : null,
          height: horizontal ? null : firstExtent,
          child: widget.first,
        ),
        divider,
        Expanded(child: widget.second),
      ];
      return horizontal
          ? Row(children: children)
          : Column(children: children);
    });
  }
}
