// The mobile assistant: one command routes to a device action (music, navigation,
// a timer) or to the accountable agent, deterministically and offline. These
// falsifiers pin the classification, the deep links a phone would open, and the
// spoken replies, all without a microphone, a speaker, or a phone.

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/assistant/assistant_intent.dart';
import 'package:flywheel_desktop/assistant/assistant_router.dart';

void main() {
  group('routeIntent', () {
    test('play commands become music with a cleaned query', () {
      expect((routeIntent('play jazz') as PlayMusic).query, 'jazz');
      expect((routeIntent('put on some lo-fi beats') as PlayMusic).query, 'lo-fi beats');
      expect((routeIntent('play the song bohemian rhapsody') as PlayMusic).query,
          'bohemian rhapsody');
      expect((routeIntent('play') as PlayMusic).query, ''); // resume
    });

    test('media transport controls are recognized', () {
      expect((routeIntent('pause') as ControlMedia).action, MediaAction.pause);
      expect((routeIntent('stop the music') as ControlMedia).action, MediaAction.pause);
      expect((routeIntent('resume') as ControlMedia).action, MediaAction.resume);
      expect((routeIntent('next song') as ControlMedia).action, MediaAction.next);
      expect((routeIntent('skip') as ControlMedia).action, MediaAction.next);
      expect((routeIntent('previous track') as ControlMedia).action, MediaAction.previous);
    });

    test('navigation captures the destination and the travel mode', () {
      final drive = routeIntent('navigate to the airport') as Navigate;
      expect(drive.destination, 'the airport');
      expect(drive.mode, TravelMode.driving);
      expect((routeIntent('walk to the park') as Navigate).mode, TravelMode.walking);
      expect((routeIntent('take me to 123 Main St by train') as Navigate).mode,
          TravelMode.transit);
      expect((routeIntent('directions to the pier by bike') as Navigate).mode,
          TravelMode.bicycling);
    });

    test('timers parse a duration; a durationless timer is not a timer', () {
      expect((routeIntent('set a timer for 5 minutes') as SetTimer).duration,
          const Duration(minutes: 5));
      expect((routeIntent('set timer for 1 hour 30 minutes') as SetTimer).duration,
          const Duration(hours: 1, minutes: 30));
      // "set a timer for later" has no duration, so it is not a timer intent
      expect(routeIntent('set a timer for later'), isA<WorkTask>());
    });

    test('anything else is work for the accountable agent', () {
      expect((routeIntent('refactor the parser module') as WorkTask).goal,
          'refactor the parser module');
      expect((routeIntent('summarize the release notes and open a PR') as WorkTask).goal,
          'summarize the release notes and open a PR');
    });

    test('an empty command is unknown, never a work task', () {
      expect(routeIntent('   '), isA<Unknown>());
    });
  });

  group('parseDuration', () {
    test('sums units and rejects text with no duration', () {
      expect(parseDuration('90 seconds'), const Duration(seconds: 90));
      expect(parseDuration('2 hours 15 min'), const Duration(hours: 2, minutes: 15));
      expect(parseDuration('soon'), isNull);
    });
  });

  group('planFor', () {
    test('a work task routes to the agent, not the device', () {
      final plan = planFor(const WorkTask('fix the flaky test'));
      expect(plan.channel, AssistantChannel.agent);
      expect(plan.taskGoal, 'fix the flaky test');
      expect(plan.deepLink, isNull);
      expect(plan.spokenReply, contains('receipts'));
    });

    test('navigation produces a maps deep link with the encoded destination', () {
      final plan = planFor(const Navigate('Blue Bottle Coffee', mode: TravelMode.walking));
      expect(plan.channel, AssistantChannel.device);
      expect(plan.deepLink, contains('destination=Blue%20Bottle%20Coffee'));
      expect(plan.deepLink, contains('travelmode=walking'));
      expect(plan.spokenReply, 'Starting walking directions to Blue Bottle Coffee.');
    });

    test('music produces a search deep link and an empty query resumes', () {
      expect(planFor(const PlayMusic('miles davis')).deepLink, endsWith('/miles%20davis'));
      expect(planFor(const PlayMusic('miles davis')).spokenReply, 'Playing miles davis.');
      expect(planFor(const PlayMusic('')).spokenReply, 'Playing your music.');
    });

    test('a timer plan carries the seconds and a spoken duration', () {
      final plan = planFor(const SetTimer(Duration(minutes: 90)));
      expect(plan.deepLink, 'timer:5400');
      expect(plan.spokenReply, 'Timer set for 1 hour 30 minutes.');
    });

    test('the maps and music providers are injectable', () {
      final links = AssistantLinks(mapsBase: 'geo:0,0?q', musicBase: 'music:search');
      expect(planFor(const Navigate('home'), links: links).deepLink,
          startsWith('geo:0,0?q&destination=home'));
      expect(planFor(const PlayMusic('rock'), links: links).deepLink, 'music:search/rock');
    });
  });

  test('humanDuration reads naturally', () {
    expect(humanDuration(const Duration(seconds: 30)), '30 seconds');
    expect(humanDuration(const Duration(minutes: 1)), '1 minute');
    expect(humanDuration(const Duration(hours: 2, minutes: 5)), '2 hours 5 minutes');
  });
}
