"""Every local flutter or dart spawn in a tracked script runs with the
analytics send suppressed.

The Flutter and Dart command line tools post build metadata to Google on each
invocation: tool version, host operating system string, locale, a session id
and a persistent client id. None of that carries operator prose or source
text. It is still a measured send from a process this repository starts.

The shape trap this file exists to catch. Four of the five spawns in this tree
use the PowerShell call operator against a resolved path variable, so
``& $flutterExe test ...`` rather than ``flutter test ...``. A detector keyed
on a line that begins with the word flutter finds one of five and reports a
clean tree, which is the worst kind of green.

Two limits on what the green here means. FLUTTER_SUPPRESS_ANALYTICS is a
request to cooperative software, so no packet is withheld and a tool that
ignored it would go unnoticed. The durable control, ``reporting=0`` in the
shared dart and flutter telemetry config under the user profile, is host state
rather than a repository fact, so no assertion reads it. A test that did would
answer differently on two machines.

This tree has zero bare dart spawns today, and a dart specific opt out
spelling has not been read out of a primary source here, so a dart spawn is
held to the flutter variable and the gap is named rather than papered over.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SUPPRESSOR = "FLUTTER_SUPPRESS_ANALYTICS"

TOOLS = ("flutter", "dart")

# Directories whose scripts are generated or vendored rather than authored
# here. None exist today; the guard keeps a future build tree from turning
# this sweep into a scan of somebody else's code.
SKIP_PARTS = ("build", ".dart_tool", "ephemeral", "node_modules", ".git")

# A script scope assignment, at column zero. PowerShell keeps $env:X for the
# life of the process once the statement runs, so a single assignment above
# the spawns covers every one of them. Indentation is refused on purpose: an
# assignment nested inside a function body or a conditional may never execute,
# and accepting it would record a suppression that never happened.
_ASSIGNMENT = re.compile(r"^\$env:" + SUPPRESSOR + r"\s*=")

# PowerShell begins a statement at the start of a line and after each of these.
_SEGMENT_BREAK = re.compile(r"[|;{}]")

_QUOTED = re.compile(r'"[^"]*"|\'[^\']*\'')

# An assignment is not a spawn, and neither is a hashtable key. Without the
# variable half, `$flutter = Resolve-Flutter ...` reads as an invocation of
# $flutter. Without the bare half, the receipt line `flutter_path = $flutter`
# reads as one too, which is a false offender that would point at a line that
# starts no process.
_ANY_ASSIGNMENT = re.compile(
    r"^\s*(?:\$[A-Za-z_][A-Za-z0-9_:]*|[A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)")

# The token in command position: an optional call operator, then a variable, a
# quoted path, or a bare name.
_COMMAND = re.compile(
    r"^\s*(?:&\s*)?(?:"
    r"\$(?P<var>[A-Za-z_][A-Za-z0-9_]*)"
    r'|"(?P<dquoted>[^"]+)"'
    r"|'(?P<squoted>[^']+)'"
    r"|(?P<bare>[^\s\"'$|;{}]+)"
    r")(?:\s|$)"
)

_SUFFIXES = (".exe", ".bat", ".cmd", ".ps1")


def _names_a_tool(token: str) -> bool:
    """Whether a command position token names flutter or dart. A path is
    reduced to its last element and a Windows suffix is dropped, so
    ``C:/src/flutter/bin/flutter.bat``, ``$flutterExe`` and a bare ``flutter``
    all answer the same."""
    name = token.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for suffix in _SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return any(name.startswith(tool) for tool in TOOLS)


def _segments(line: str) -> list:
    """One line cut into statements, ignoring separators inside a string. Cut
    positions are read from a copy with quoted spans blanked out and the
    pieces are sliced from the original, so a semicolon inside a message does
    not start a statement while a quoted executable path survives intact."""
    masked = _QUOTED.sub(
        lambda m: m.group(0)[0] + "\x00" * (len(m.group(0)) - 2)
        + m.group(0)[-1], line)
    out, start = [], 0
    for break_at in _SEGMENT_BREAK.finditer(masked):
        out.append(line[start:break_at.start()])
        start = break_at.end()
    out.append(line[start:])
    return out


def spawns(text: str) -> list:
    """Every line that puts flutter or dart in command position, as
    ``(line_number, source)`` pairs. A full line comment is skipped. A line is
    reported once however many of its segments match. Where a tool is named in
    a string or handed to Get-Command, another word holds the position."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        for segment in _segments(line):
            if not segment.strip() or _ANY_ASSIGNMENT.match(segment):
                continue
            match = _COMMAND.match(segment)
            if match is None:
                continue
            token = (match.group("var") or match.group("dquoted")
                     or match.group("squoted") or match.group("bare"))
            if _names_a_tool(token):
                found.append((number, line.strip()))
                break
    return found


def suppressed_from(text: str) -> "int | None":
    """The first line from which the suppression holds, or None."""
    for number, line in enumerate(text.splitlines(), start=1):
        if _ASSIGNMENT.match(line):
            return number
    return None


def unsuppressed_in(text: str) -> list:
    """Spawns that run before any script scope assignment, or with none."""
    first = suppressed_from(text)
    return [row for row in spawns(text) if first is None or row[0] < first]


def scripts() -> list:
    out = []
    for path in sorted(ROOT.rglob("*.ps1")):
        if any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts):
            continue
        out.append(path)
    return out


# --- the sweep ---------------------------------------------------------------

def test_every_local_flutter_invocation_is_suppressed():
    """The assertion of record. Five spawns in three scripts as of the change
    that added the assignments; before it, all five were unsuppressed."""
    offenders = []
    for path in scripts():
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, source in unsuppressed_in(text):
            offenders.append(
                str(path.relative_to(ROOT)) + ":" + str(number) + " " + source)
    assert offenders == []


def test_the_sweep_reads_real_invocations_rather_than_finding_nothing():
    """The anti vacuous control. A detector that matched nothing would pass
    the sweep above on any tree, including one where every spawn phones home.
    Bounded below rather than pinned, so adding a suppressed spawn does not
    break an unrelated change."""
    total = sum(len(spawns(p.read_text(encoding="utf-8", errors="replace")))
                for p in scripts())
    assert len(scripts()) >= 6
    assert total >= 5


# --- the shapes --------------------------------------------------------------

BARE = "flutter build windows --release"
CALL_VAR = "& $flutter pub get"
CALL_VAR_SUFFIXED = "& $flutterExe test test/a_test.dart --reporter expanded"
CALL_PATH = '& "C:/src/flutter/bin/flutter.bat" doctor'
INDENTED = "    flutter test"


def test_the_detector_sees_the_call_operator_and_not_only_the_bare_word():
    """The correction that made this file necessary. Four of the five real
    spawns are the call operator shape, so a bare word regex reports one."""
    text = "\n".join([BARE, CALL_VAR, CALL_VAR_SUFFIXED, CALL_PATH, INDENTED])
    assert [row[0] for row in spawns(text)] == [1, 2, 3, 4, 5]


def test_a_dart_spawn_is_detected_even_though_this_tree_has_none():
    text = "\n".join(["dart run tool/x.dart", "& $dartExe format ."])
    assert len(spawns(text)) == 2


def test_a_spawn_after_a_pipe_or_a_brace_is_still_in_command_position():
    text = "\n".join(["Get-Content x | flutter pub add -",
                      "if ($ok) { flutter clean }"])
    assert len(spawns(text)) == 2


# --- what is not a spawn -----------------------------------------------------

def test_resolving_the_tool_is_not_running_it():
    """Get-Command reads PATH. No child starts, so nothing is sent."""
    text = "$cmd = Get-Command flutter -ErrorAction SilentlyContinue"
    assert spawns(text) == []


def test_naming_the_tool_in_a_message_is_not_running_it():
    text = "\n".join(['Write-Output "-- flutter build windows --release"',
                      'throw "flutter pub get failed with exit code $e"',
                      '  $logPath = Join-Path $root "flutter-test.log"'])
    assert spawns(text) == []


def test_a_comment_is_not_a_spawn():
    """The block this change inserts names the tools in prose. A detector that
    read comments would report its own documentation as a leak."""
    text = "\n".join(["# The flutter and dart CLIs post build metadata.",
                      "   # flutter build windows --release"])
    assert spawns(text) == []


def test_a_continuation_flag_is_not_a_command():
    text = '    --dart-define "BULLETIN_GATEWAY_FIXTURE=$configPath"'
    assert spawns(text) == []


def test_assigning_the_resolved_path_is_not_a_spawn():
    text = "\n".join(["$flutter = Resolve-FlutterExecutable $FlutterPath",
                      '$flutterExe = Resolve-Executable $FlutterPath @("flutter")'])
    assert spawns(text) == []


def test_a_hashtable_key_named_for_the_tool_is_not_a_spawn():
    """Both run scripts write the resolved path into their receipt as
    `flutter_path = $flutter`. A bare word before an equals sign is a key or a
    named argument, and reporting it would point an offender line at a
    statement that starts no process."""
    text = "\n".join(["  flutter_path = $flutter",
                      "  flutter_path = $flutterExe"])
    assert spawns(text) == []


def test_a_separator_inside_a_message_does_not_start_a_statement():
    """The decoder script carries `"build/windows/x64 absent; Flutter will
    build it"`, and splitting the raw line puts Flutter in what reads as
    command position, inside a string."""
    text = ('return @{ attempted = $false; '
            'reason = "build/windows/x64 absent; Flutter will build it" }')
    assert spawns(text) == []


# --- the false success controls ----------------------------------------------

def test_a_script_with_no_assignment_reports_every_spawn():
    """The state of all three scripts before this change. If this test ever
    passes with an empty list the sweep above proves nothing."""
    text = "\n".join(['$ErrorActionPreference = "Stop"', CALL_VAR, BARE])
    assert len(unsuppressed_in(text)) == 2


def test_an_assignment_below_the_spawn_does_not_cover_it():
    """Order is the whole mechanism. The variable is read by the child at
    spawn time, so a later assignment covers later children only."""
    text = "\n".join([CALL_VAR, "$env:" + SUPPRESSOR + ' = "true"', BARE])
    rows = unsuppressed_in(text)
    assert [row[0] for row in rows] == [1]


def test_an_indented_assignment_does_not_count_as_script_scope():
    """An assignment inside a function body or a conditional may never run, so
    refusing it is stricter than PowerShell requires. The alternative green
    lights a suppression nothing executed."""
    text = "\n".join(['  $env:' + SUPPRESSOR + ' = "true"', BARE])
    assert len(unsuppressed_in(text)) == 1


def test_the_assignment_this_change_writes_is_the_one_the_detector_accepts():
    """Pins the exact text inserted into the three scripts. A future rewrite
    that changes the spelling fails here rather than silently disabling the
    sweep."""
    line = '$env:' + SUPPRESSOR + ' = "true"'
    assert suppressed_from(line) == 1
    assert unsuppressed_in("\n".join([line, BARE, CALL_VAR])) == []


def test_each_edited_script_carries_the_assignment_above_its_first_spawn():
    """Named rather than inferred from the sweep, so removing the assignment
    from one script points at that script."""
    edited = ("desktop/scripts/build_installer.ps1",
              "desktop/tool/run_bulletin_media_decoder_smoke.ps1",
              "desktop/tool/run_bulletin_media_gateway_e2e.ps1")
    for relative in edited:
        text = (ROOT / relative).read_text(encoding="utf-8", errors="replace")
        first_assignment = suppressed_from(text)
        rows = spawns(text)
        assert first_assignment is not None, relative
        assert rows, relative
        assert first_assignment < rows[0][0], relative
