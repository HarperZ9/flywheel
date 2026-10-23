# Desktop engine startup

The installed desktop can start its bundled engine when the initial connection
to the default local gateway is refused. It makes one automatic attempt per
window lifecycle. The engine launches directly from the installation's `engine`
directory, using the existing hidden Windows process path.

The desktop reports startup before it reports readiness. A later successful
gateway status read enables connected views and refreshes Journey reads. Lanes and
model endpoints report their own health once the gateway answers.

Automatic startup runs for the fresh local default connection in an installed
desktop with a bundled engine, when the gateway refuses the connection with
Windows code `1225` or `10061`, or `61` or `111` on systems that report those
codes. Every other case leaves startup to you: a remote or paired connection, a
mobile client, any saved connection file (including damaged or empty
configuration), a checkout without a bundled engine, and a timeout,
authentication error, server error, incompatible API or malformed status
response, since an engine may be running behind any of those. Clearing a saved
connection restores the fresh local default.

If startup fails or an engine subsequently exits, use **Start engine** to retry.
Repeated status polls do not create a restart loop. If the bundle disappears
between discovery and launch, automatic startup reports it missing instead of
switching to an executable on PATH. Explicit manual startup retains the existing
development fallback.

Closing the desktop stops the child it started. An engine that was already
running keeps running. If process creation settles after the
window closes, the existing late-start cleanup handles the owned child.

The startup tests cover transport outcomes, a single launch and recovery,
failure without repeated launches, late completion, missing-bundle refusal,
and the shell's bundled-only startup wiring. Installed UI acceptance, provider
authentication and tool integration have their own release checks.
