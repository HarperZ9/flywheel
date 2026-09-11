import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

bool rowanIsVisible(BuildContext context) {
  final box = context.findRenderObject();
  if (box is! RenderBox || !box.attached || !box.hasSize || box.size.isEmpty) {
    return false;
  }
  var visible = MatrixUtils.transformRect(
      box.getTransformTo(null), Offset.zero & box.size);
  final screen = Offset.zero & MediaQuery.sizeOf(context);
  visible = visible.intersect(screen);
  RenderObject? parent = box.parent;
  while (parent != null && !visible.isEmpty) {
    if (parent is RenderOffstage && parent.offstage) return false;
    if (parent is RenderOpacity && parent.opacity == 0) return false;
    if (parent is RenderBox &&
        parent.hasSize &&
        (parent is RenderAbstractViewport || parent is RenderClipRect)) {
      visible = visible.intersect(MatrixUtils.transformRect(
          parent.getTransformTo(null), Offset.zero & parent.size));
    }
    parent = parent.parent;
  }
  return !visible.isEmpty;
}

/// Visibility is re-evaluated after actual paint, with no offscreen poll timer.
class RowanPaintObserver extends SingleChildRenderObjectWidget {
  const RowanPaintObserver(
      {super.key, required this.onPaint, required super.child});
  final VoidCallback onPaint;

  @override
  RenderObject createRenderObject(BuildContext context) =>
      RowanPaintRenderObserver(onPaint);

  @override
  void updateRenderObject(
      BuildContext context, covariant RowanPaintRenderObserver renderObject) {
    renderObject.onPaint = onPaint;
  }
}

class RowanPaintRenderObserver extends RenderProxyBox {
  RowanPaintRenderObserver(this.onPaint);
  VoidCallback onPaint;

  @override
  void paint(PaintingContext context, Offset offset) {
    super.paint(context, offset);
    onPaint();
  }
}
