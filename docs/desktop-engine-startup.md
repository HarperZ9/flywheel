# Desktop engine startup

The installed desktop can start its bundled engine when the initial connection
to the default local gateway is refused. It makes one automatic attempt per
window lifecycle. The engine launches directly from the installation's `engine`
directory, using the existing hidden Windows process path.

The desktop reports startup before it reports readiness. A later successful
gateway status read enables connected views and refreshes Journey reads. Starting
a process alone does not establish that its lanes or model endpoints work.

Automatic startup does not run for a remote or paired connection, a mobile
client, any saved connection file (including damaged or empty configuration),
or a checkout without a bundled engine. Clearing a saved connection restores
the fresh local default. It also does not run on a
timeout, authentication error, server error, incompatible API, or malformed
status response. Those conditions do not establish that the engine is absent.
Unsupported operating-system refusal codes leave startup manual.
Windows refusal codes `1225` and `10061` are supported, alongside `61` and `111`
on systems that report those connection-refused codes.

If startup fails or an engine subsequently exits, use **Start engine** to retry.
Repeated status polls do not create a restart loop. If the bundle disappears
between discovery and launch, automatic startup reports it missing instead of
switching to an executable on PATH. Explicit manual startup retains the existing
development fallback.

Closing the desktop stops only a child it owns. An engine that was already
running remains outside that ownership. If process creation settles after the
window closes, the existing late-start cleanup handles the owned child.

The startup tests cover transport outcomes, a single launch and recovery,
failure without repeated launches, late completion, missing-bundle refusal,
and the shell's bundled-only startup wiring. These tests do not establish
installed UI acceptance, provider authentication, or complete tool integration.
