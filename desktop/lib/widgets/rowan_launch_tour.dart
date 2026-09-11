// rowan_launch_tour.dart -- the first-run walkthrough Rowan gives over the
// shell. It is the demo and the marketing capture as well as the tour: it
// renders with no gateway, no keys, and no Journey, so the same widget drives
// a live first launch, a screen recording, and a golden on any machine.
//
// It deliberately reuses RowanPresenter (the shader avatar, already reduced
// motion, theme, and a11y safe) and does NOT mount RowanWalkthroughPanel. That
// panel needs a live engine, an endpoint, a model, and a Journey binding, none
// of which exist at first launch. The live walkthrough keeps its one home in
// the Studio; the final step of this tour bridges there.
import 'package:flutter/material.dart';

import '../accessibility/motion.dart';
import '../assistant/assistant_identity.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'rowan_presenter.dart';

/// One tour step. [body] is a plain description; [note] is an honest-null
/// callout when a step names a boundary the app does not claim past.
class _TourStep {
  final String kicker;
  final String title;
  final String body;
  final String? note;
  const _TourStep(this.kicker, this.title, this.body, {this.note});
}

/// The steps, in order. Step 0 shows the avatar; the rest are copy cards. The
/// wording stays feature-first and keeps its honest nulls: what is rechecked,
/// what is not claimed, and that the avatar is a drawing rather than a model.
const _steps = <_TourStep>[
  _TourStep(
    AssistantIdentity.name,
    "I'm Rowan.",
    "Flywheel's assistant, on the model you choose. This is a quick look at "
        'what the app does. The avatar above is drawn live on your machine. It '
        'is a rendered visual, not a claim about any model. Turn it, open it, '
        'or switch motion on.',
  ),
  _TourStep(
    'THE RUN',
    'Run a task, keep the record',
    'Flywheel runs an AI task with the model and tools you pick, local or '
        'hosted. As it runs it writes a record of what happened, so someone who '
        'was not there can check the run later.',
  ),
  _TourStep(
    'RECEIPTS',
    'Each reply shows its state',
    'Every reply carries one of three states: verified, drift, or '
        'unverifiable. The recheck reads a sealed chain of tool-call receipts '
        'and needs no network and no model to run.',
  ),
  _TourStep(
    'THE LIMIT',
    'What the record does not claim',
    'The record is honest about its own edges, and so is this tour.',
    note: 'The map of command names is kept by hand, so a command Flywheel has '
        'never seen is allowed and written down as unknown. An unchecked value '
        'never reads as a confirmed one. The app is tested, not proven adopted.',
  ),
  _TourStep(
    'NEXT',
    'See a run in the Studio',
    'The Studio runs a real walkthrough once the engine is up and a model is '
        'chosen. Open it when you are ready, or close this and explore on your '
        'own.',
  ),
];

/// Show the first-run walkthrough over the current screen. [onOpenStudio], when
/// given, is called from the final step to take the user to the Studio; the
/// dialog pops first. Returns when the dialog is dismissed.
Future<void> showRowanWalkthrough(
  BuildContext context, {
  VoidCallback? onOpenStudio,
}) {
  return showDialog<void>(
    context: context,
    barrierDismissible: true,
    barrierLabel: 'Close the ${AssistantIdentity.name} walkthrough',
    builder: (ctx) => RowanWalkthroughTour(onOpenStudio: onOpenStudio),
  );
}

class RowanWalkthroughTour extends StatefulWidget {
  const RowanWalkthroughTour({super.key, this.onOpenStudio});

  /// Called from the last step to move the user into the Studio. The dialog is
  /// popped before this runs. Null hides the Studio action.
  final VoidCallback? onOpenStudio;

  @override
  State<RowanWalkthroughTour> createState() => _RowanWalkthroughTourState();
}

class _RowanWalkthroughTourState extends State<RowanWalkthroughTour> {
  int _step = 0;

  bool get _isFirst => _step == 0;
  bool get _isLast => _step == _steps.length - 1;

  void _next() {
    if (_isLast) return;
    setState(() => _step += 1);
  }

  void _back() {
    if (_isFirst) return;
    setState(() => _step -= 1);
  }

  void _openStudio() {
    Navigator.of(context).maybePop();
    widget.onOpenStudio?.call();
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final step = _steps[_step];
    return Dialog(
      backgroundColor: t.ground,
      insetPadding: const EdgeInsets.all(FwLayout.s4),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 480, maxHeight: 640),
        child: Padding(
          padding: const EdgeInsets.all(FwLayout.s5),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _topBar(context),
              const SizedBox(height: FwLayout.s3),
              Flexible(
                child: SingleChildScrollView(
                  child: AnimatedSwitcher(
                    duration: motionDuration(context),
                    child: Column(
                      key: ValueKey(_step),
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if (_isFirst) ...[
                          const RowanPresenter(),
                          const SizedBox(height: FwLayout.s4),
                        ],
                        Kicker(step.kicker),
                        const SizedBox(height: FwLayout.s2),
                        Semantics(
                          header: true,
                          child: Text(step.title,
                              style: Theme.of(context).textTheme.titleLarge),
                        ),
                        const SizedBox(height: FwLayout.s2),
                        Text(step.body,
                            style: TextStyle(
                                color: t.inkSoft, fontSize: 13.5, height: 1.5)),
                        if (step.note != null) ...[
                          const SizedBox(height: FwLayout.s3),
                          HonestNull(step.note!),
                        ],
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(height: FwLayout.s4),
              _controls(context),
            ],
          ),
        ),
      ),
    );
  }

  Widget _topBar(BuildContext context) {
    final t = context.fw;
    return Row(
      children: [
        Expanded(
          child: Text('Step ${_step + 1} of ${_steps.length}',
              style: fwKicker(t, size: 10, color: t.inkFaint)),
        ),
        TextButton(
          onPressed: () => Navigator.of(context).maybePop(),
          child: const Text('Skip'),
        ),
      ],
    );
  }

  Widget _controls(BuildContext context) {
    final t = context.fw;
    return Row(
      children: [
        _dots(t),
        const SizedBox(width: FwLayout.s3),
        // The trailing actions reflow to a second run on a narrow dialog rather
        // than overflow the row. On a normal width they sit on one line, right
        // aligned, so the common case looks unchanged.
        Expanded(
          child: Wrap(
            alignment: WrapAlignment.end,
            spacing: FwLayout.s2,
            runSpacing: FwLayout.s2,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              if (!_isFirst)
                TextButton(onPressed: _back, child: const Text('Back')),
              if (!_isLast)
                FilledButton(onPressed: _next, child: const Text('Next'))
              else if (widget.onOpenStudio != null) ...[
                TextButton(
                  onPressed: () => Navigator.of(context).maybePop(),
                  child: const Text('Done'),
                ),
                FilledButton(
                  onPressed: _openStudio,
                  child: const Text('Explore the Studio'),
                ),
              ] else
                FilledButton(
                  onPressed: () => Navigator.of(context).maybePop(),
                  child: const Text('Done'),
                ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _dots(FwTokens t) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < _steps.length; i++)
          Container(
            width: 6,
            height: 6,
            margin: const EdgeInsets.only(right: FwLayout.s1),
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: i == _step ? t.ink : t.line,
            ),
          ),
      ],
    );
  }
}
