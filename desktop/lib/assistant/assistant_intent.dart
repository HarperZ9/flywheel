// assistant_intent.dart -- what a spoken or typed command asks the agent to do.
//
// The mobile assistant reads one command and routes it to one of two channels: a
// WorkTask goes to the accountable agent (relay, over the gateway), so real work
// stays witnessed and re-verifiable; a device intent (music, navigation, a timer)
// is a quick local action the phone performs and gets out of the way. The types
// are a sealed set so the planner switches over them exhaustively, and every field
// is plain data, so routing and planning are pure and fully testable without a
// microphone, a speaker, or a phone.

/// How a directions request should travel.
enum TravelMode { driving, walking, transit, bicycling }

/// A media transport control.
enum MediaAction { pause, resume, next, previous }

/// Which surface carries out a plan: the accountable agent, or the device.
enum AssistantChannel { agent, device }

sealed class AssistantIntent {
  const AssistantIntent();
}

/// A work request, handed to the accountable agent (relay via the gateway) so the
/// run is witnessed and the receipts travel with it.
class WorkTask extends AssistantIntent {
  const WorkTask(this.goal);
  final String goal;
}

/// Play or search for music. An empty query means resume whatever is queued.
class PlayMusic extends AssistantIntent {
  const PlayMusic(this.query);
  final String query;
}

/// A media transport control (pause, resume, skip).
class ControlMedia extends AssistantIntent {
  const ControlMedia(this.action);
  final MediaAction action;
}

/// Start navigation to a place.
class Navigate extends AssistantIntent {
  const Navigate(this.destination, {this.mode = TravelMode.driving});
  final String destination;
  final TravelMode mode;
}

/// Set a countdown timer.
class SetTimer extends AssistantIntent {
  const SetTimer(this.duration);
  final Duration duration;
}

/// The command was empty or could not be understood.
class Unknown extends AssistantIntent {
  const Unknown(this.text);
  final String text;
}
