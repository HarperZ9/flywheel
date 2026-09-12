/// Flywheel's persistent assistant display identity, independent of model choice.
/// Keep provider roles, route IDs, and stored conversation keys unchanged.
///
/// Rowan is the face and the voice of Flywheel. The wording here is warm and
/// plain-spoken to match that, and it still states the two facts a user needs
/// on the first screen: the model is the one you choose, and every reply shows
/// its receipt state. The spoken voice lives in assistant/rowan_voice_profile.dart.
abstract final class AssistantIdentity {
  static const name = 'Rowan';
  static const abbreviation = 'RW';
  static const openLabel = 'Open $name';
  static const welcome = "I'm $name.";
  static const introduction =
      "I'm the assistant for Flywheel, running on the model you choose. "
      'Every reply shows its receipt state, so you can check the work yourself.';
}
