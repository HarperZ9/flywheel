// assistant_router.dart -- turn one command into an intent, then into a plan.
//
// routeIntent classifies a spoken or typed command deterministically: clear device
// commands (play, pause, skip, navigate, set a timer) are matched cheaply and
// offline, and everything else falls through to a WorkTask for the accountable
// agent. planFor then turns an intent into an AssistantPlan: a device deep link the
// phone opens, or a task goal the agent runs, plus the line the assistant speaks
// back. Both are pure, so the whole surface is testable without a microphone, a
// speaker, or a phone; the platform layer (speech in, speech out, launching the
// link, posting the task) is the only part that needs the device.

import 'assistant_intent.dart';

final _play = RegExp(r'^(?:play|put on|start playing)\b\s*(.*)$', caseSensitive: false);
final _pause =
    RegExp(r'^pause(?:\s+(?:the\s+)?music)?[.!]?$|^stop\s+(?:the\s+)?music[.!]?$',
        caseSensitive: false);
final _resume = RegExp(
    r'^(?:resume|unpause|continue(?:\s+playing)?)(?:\s+(?:the\s+)?music)?[.!]?$',
    caseSensitive: false);
final _next =
    RegExp(r'^(?:next|skip)(?:\s+(?:this\s+)?(?:song|track))?[.!]?$', caseSensitive: false);
final _prev =
    RegExp(r'^(?:previous|last)(?:\s+(?:song|track))?[.!]?$', caseSensitive: false);
final _navTo = RegExp(
    r'^(?:navigate|take me|directions|drive|walk|go|head)\s+to\s+(.+)$',
    caseSensitive: false);
final _navBare = RegExp(r'^navigate\s+(.+)$', caseSensitive: false);
final _timer = RegExp(r'^set\s+(?:a\s+)?timer\s+for\s+(.+)$', caseSensitive: false);
final _durUnit = RegExp(r'(\d+)\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b',
    caseSensitive: false);

/// Classify a command. Device commands match cheaply; anything else is work.
AssistantIntent routeIntent(String command) {
  final c = command.trim();
  if (c.isEmpty) return const Unknown('');
  final low = c.toLowerCase();

  if (_pause.hasMatch(low)) return const ControlMedia(MediaAction.pause);
  if (_resume.hasMatch(low)) return const ControlMedia(MediaAction.resume);
  if (_next.hasMatch(low)) return const ControlMedia(MediaAction.next);
  if (_prev.hasMatch(low)) return const ControlMedia(MediaAction.previous);

  final play = _play.firstMatch(c);
  if (play != null) return PlayMusic(_cleanMusic(play.group(1) ?? ''));

  final timer = _timer.firstMatch(low);
  if (timer != null) {
    final d = parseDuration(timer.group(1)!);
    if (d != null && d > Duration.zero) return SetTimer(d);
  }

  final nav = _navTo.firstMatch(c) ?? _navBare.firstMatch(c);
  if (nav != null) return Navigate(_stripTrailing(nav.group(1)!), mode: _travelMode(low));

  return WorkTask(c);
}

/// Sum every number-and-unit pair in the text, or null when there is no duration.
Duration? parseDuration(String text) {
  var total = Duration.zero;
  var found = false;
  for (final m in _durUnit.allMatches(text.toLowerCase())) {
    final n = int.tryParse(m.group(1)!);
    if (n == null) continue;
    found = true;
    final unit = m.group(2)!;
    if (unit.startsWith('h')) {
      total += Duration(hours: n);
    } else if (unit.startsWith('m')) {
      total += Duration(minutes: n);
    } else {
      total += Duration(seconds: n);
    }
  }
  return found ? total : null;
}

String _cleanMusic(String query) {
  var s = query.trim();
  s = s.replaceFirst(
      RegExp(r'^(?:some|the song|a song|the album|the playlist)\s+', caseSensitive: false),
      '');
  return _stripTrailing(s.replaceFirst(RegExp(r'\s+please[.!]?$', caseSensitive: false), ''));
}

String _stripTrailing(String s) => s.replaceFirst(RegExp(r'[\s.,!?]+$'), '').trim();

TravelMode _travelMode(String low) {
  if (low.contains('walk')) return TravelMode.walking;
  if (RegExp(r'\b(?:transit|bus|train|subway|public transport)\b').hasMatch(low)) {
    return TravelMode.transit;
  }
  if (RegExp(r'\b(?:bike|bicycle|cycling)\b').hasMatch(low)) return TravelMode.bicycling;
  return TravelMode.driving;
}

/// The concrete result of routing: which channel carries it out, the device deep
/// link or the agent task goal, and the line the assistant speaks back.
class AssistantPlan {
  const AssistantPlan({
    required this.intent,
    required this.channel,
    required this.spokenReply,
    this.deepLink,
    this.taskGoal,
  });

  final AssistantIntent intent;
  final AssistantChannel channel;
  final String spokenReply;
  final String? deepLink;
  final String? taskGoal;
}

/// The deep-link targets for device actions, injectable so a test is deterministic
/// and the maps or music provider can be swapped.
class AssistantLinks {
  const AssistantLinks({
    this.mapsBase = 'https://www.google.com/maps/dir/?api=1',
    this.musicBase = 'https://open.spotify.com/search',
  });

  final String mapsBase;
  final String musicBase;

  String navigate(String destination, TravelMode mode) =>
      '$mapsBase&destination=${Uri.encodeComponent(destination)}&travelmode=${mode.name}';

  String music(String query) =>
      query.isEmpty ? musicBase : '$musicBase/${Uri.encodeComponent(query)}';
}

/// Turn an intent into a plan. Exhaustive over the sealed intent set.
AssistantPlan planFor(AssistantIntent intent,
        {AssistantLinks links = const AssistantLinks()}) =>
    switch (intent) {
      WorkTask(:final goal) => AssistantPlan(
          intent: intent,
          channel: AssistantChannel.agent,
          taskGoal: goal,
          spokenReply: 'On it. I will start on that and keep the receipts.'),
      Navigate(:final destination, :final mode) => AssistantPlan(
          intent: intent,
          channel: AssistantChannel.device,
          deepLink: links.navigate(destination, mode),
          spokenReply: 'Starting ${mode.name} directions to $destination.'),
      PlayMusic(:final query) => AssistantPlan(
          intent: intent,
          channel: AssistantChannel.device,
          deepLink: links.music(query),
          spokenReply: query.isEmpty ? 'Playing your music.' : 'Playing $query.'),
      ControlMedia(:final action) => AssistantPlan(
          intent: intent,
          channel: AssistantChannel.device,
          deepLink: 'media:${action.name}',
          spokenReply: switch (action) {
            MediaAction.pause => 'Paused.',
            MediaAction.resume => 'Resumed.',
            MediaAction.next => 'Skipping ahead.',
            MediaAction.previous => 'Going back.',
          }),
      SetTimer(:final duration) => AssistantPlan(
          intent: intent,
          channel: AssistantChannel.device,
          deepLink: 'timer:${duration.inSeconds}',
          spokenReply: 'Timer set for ${humanDuration(duration)}.'),
      Unknown(:final text) => AssistantPlan(
          intent: intent,
          channel: AssistantChannel.device,
          spokenReply: text.isEmpty
              ? 'I did not catch that.'
              : 'I am not sure how to help with that one yet.'),
    };

/// A short spoken form of a duration, e.g. "1 hour 30 minutes".
String humanDuration(Duration d) {
  final h = d.inHours, m = d.inMinutes.remainder(60), s = d.inSeconds.remainder(60);
  final parts = <String>[];
  if (h > 0) parts.add('$h hour${h == 1 ? '' : 's'}');
  if (m > 0) parts.add('$m minute${m == 1 ? '' : 's'}');
  if (s > 0 && h == 0) parts.add('$s second${s == 1 ? '' : 's'}');
  return parts.isEmpty ? '0 seconds' : parts.join(' ');
}
