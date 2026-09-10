# Rowan

Rowan is the permanent name of Flywheel's assistant. Flywheel remains the
product name. The desktop source of truth is
`desktop/lib/assistant/assistant_identity.dart`; chat, navigation, and the
assistant panel use those constants on each launch.

The name is independent of the selected model or provider. Model selectors
continue to show the actual model, and receipt state remains visible. Rowan
does not claim to be a particular model, a human, or a separate execution engine.

This identity change preserves `DestinationId.chat`, provider roles such as
`assistant`, conversation IDs, storage keys, and existing chat history. It adds
no storage migration or new preference. It does not prepend identity text to
model requests or change prompt hashes, approval scope, or provider instructions.
The welcome identifies the app's assistant; model-generated self-identification
is still determined by the selected model and its existing context.

Rowan's goals are useful work, clear evidence, reliable tools, and continuity
across Flywheel workflows. Comparative superiority is a goal to evaluate, not a
claim established by this name or interface. Claims about capabilities require
their own evidence and must retain their limits.

Avatar selection and custom artwork are separate work. This change retains the
existing iconography.
