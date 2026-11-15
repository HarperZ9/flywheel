# Privacy

Learn's plugin runs on your computer. The publisher operates no backend, account or
inference service for it, and the plugin collects no telemetry or usage statistics.

**What it reads.** The arguments the connected model passes to a tool call, and files
inside the Learn state folder that a call names.

**What it stores.** Study sessions and the practice answers you choose to record, as
JSON files inside the Learn state folder. That folder is `LEARN_HOME` when set, or
else `%LOCALAPPDATA%\learn` on Windows, `~/Library/Application Support/learn` on
macOS and `$XDG_DATA_HOME/learn` (default `~/.local/share/learn`) on Linux. Only the
tutor plan and tutor record tools write, and only inside that folder.

**What it sends.** Nothing. The packaged tools open no network connection. Live course
automation is not part of this package.

**Retention.** Files stay until you delete them. Deleting a session file, or the whole
state folder, removes that data. Learn keeps no other copy.

**Third parties.** The connected client and its model see tool arguments and results
under that client's terms. Your model provider's privacy policy applies to what the
model reads.

**Support and security reports.** https://github.com/HarperZ9/learn/issues
