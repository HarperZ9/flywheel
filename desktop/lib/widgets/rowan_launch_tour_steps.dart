// rowan_launch_tour_steps.dart -- the copy for the first-run walkthrough,
// kept beside the widget that renders it (rowan_launch_tour.dart) so the tour
// logic stays small and the wording is easy to read and revise in one place.
//
// The walkthrough is a shipped, public-facing surface, so the copy stays
// feature-first and keeps its honest nulls: what is rechecked, what is not
// claimed, the measured bound on the one lift it cites, and that the avatar is
// a drawing rather than a model. It names no file paths and makes no claim the
// engine cannot show.
part of 'rowan_launch_tour.dart';

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
/// arc runs: who Rowan is, what the app does, how you work with it, the receipt
/// mechanism, what is finished, what is not claimed yet, what it is built on,
/// where it goes, and an invitation to try it with or without the assistant.
const _steps = <_TourStep>[
  _TourStep(
    AssistantIdentity.name,
    "I'm Rowan.",
    "Flywheel's assistant, on the model you choose. Ask for work in plain "
        'words and I turn it into a task the app runs and keeps a record of. I '
        'can start a run and read back tasks the gateway already holds, then '
        'show you where each one stands. If a submission gets lost I tell you '
        'rather than sending it a second time. A result I cannot check stays '
        'marked that way. The avatar above is drawn live on your machine. It '
        'is a rendered visual, not a claim about any model. Turn it, open it, '
        'or switch motion on.',
  ),
  _TourStep(
    'THE APP',
    'One place for the whole loop',
    'Flywheel is where you run AI work and keep the proof of it. You edit '
        'code in it and run the coding agent from it. You pick the model, '
        'local or hosted, and bring your own key. While a task runs, every '
        'tool call the agent makes gets written down as it happens, so the '
        'work and its record grow together.',
  ),
  _TourStep(
    'TOGETHER',
    'You ask, the app keeps the record',
    'You can drive Flywheel yourself, or hand a task to me. The run is the '
        'same either way, and it leaves the same record. While a task is going '
        'I refresh it every few seconds so you can watch it move. I also pick '
        'up tasks that started somewhere else, so a run you began on another '
        'device shows up here. Starting a task sends only your goal. Anything '
        'that publishes or reaches outside the app asks you first.',
  ),
  _TourStep(
    'RECEIPTS',
    'Each reply shows its state',
    'Every reply carries one of three states: verified, drift, or '
        'unverifiable. The recheck reads a sealed chain of the run\'s '
        'tool-call receipts. It needs no network and no model to run, so you '
        'can check a reply on the machine in front of you.',
  ),
  _TourStep(
    'TODAY',
    'What runs today',
    'The app ships as a desktop client and as a command you can install. It '
        'runs tasks across several model providers and on a local model '
        'trained for this work. The recheck runs today and the three states '
        'show on every reply. The receipts behind them are covered by the test '
        'suite. On a screened set of 61 hard coding tasks the local model '
        'missed on its first try, letting an outside test pick the best of '
        'four attempts raised the pass rate from 5% to 25%.',
  ),
  _TourStep(
    'STILL OPEN',
    'What we do not claim yet',
    'The record is honest about its own edges, and so is this walkthrough.',
    note: 'That lift is measured on one screened set with one model, and there '
        'is no comparison against a frontier system yet. The local training '
        'did not beat the base model on a general coding benchmark. The map of '
        'command names is kept by hand, so a command Flywheel has never seen is '
        'allowed and written down as unknown. An unchecked value never reads '
        'as a confirmed one. The app is tested, not proven adopted.',
  ),
  _TourStep(
    'THE IDEA',
    'The work speaks for itself',
    'One idea holds the app together. A good answer should not need a famous '
        'name behind it. A model can write expert-shaped output for anyone '
        'now, so the finished work no longer tells you who is good for it. '
        'Flywheel settles that by deciding acceptance with a check the author '
        'cannot edit, and by handing you a receipt a stranger can re-run. The '
        'check is written outside the model, and no trained model sits in the '
        'deciding path. It runs on a machine you already own, so being taken '
        'seriously does not come down to who can pay the most.',
  ),
  _TourStep(
    "WHAT'S NEXT",
    'Built to grow on its proof',
    'What exists now is the floor. Every result carries a receipt, and every '
        'accept has to clear a check the model did not write. The next work '
        'turns that measured lift into a settled result on a larger test set. '
        'After that comes teaching the local model on its own verified runs, '
        'and adding depth for more kinds of work. Each step ships with its own '
        'tests and its own record. A step that cannot show its work does not '
        'ship.',
  ),
  _TourStep(
    'YOUR TURN',
    'Give it a try',
    'You do not need me to use Flywheel. Run a task yourself and read the '
        'record it leaves, or hand one to me and watch it move. The Studio '
        'runs a full walkthrough on a live engine once you have picked a '
        'model. Open it when you are ready, or close this and look around on '
        'your own.',
  ),
];
