/// Flywheel's persistent assistant display identity, independent of model choice.
/// Keep provider roles, route IDs, and stored conversation keys unchanged.
abstract final class AssistantIdentity {
  static const name = 'Rowan';
  static const abbreviation = 'RW';
  static const openLabel = 'Open $name';
  static const welcome = "I'm $name.";
  static const introduction = "Flywheel's assistant, on the model you choose. "
      'Receipt state is shown on each reply.';
}
