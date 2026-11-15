"""Options the editing commands share: plan, submit, judge, fix and polish.

articulate.cli registers the commands and calls these helpers, so the option
code lives in one place and the core command line stays small.

  --allow-change KINDS  protected change kinds the edit may make (plan, fix,
                        polish). Each accepted change is reported.
  --config PATH|none    the project config (plan, judge, fix, polish).
  --explain [json|text] a change report for an accepted edit (fix, polish,
                        submit): json adds `changes` to the result, text prints
                        a readable report instead of the JSON.
"""
import json

from . import changes, cli_config, edit_options


def add_arguments(parser, cmd):
    """Register the shared editing options for one subcommand."""
    if cmd in ("plan", "fix", "polish"):
        parser.add_argument(
            "--allow-change", default=None, metavar="KINDS",
            help="comma-separated protected change kinds the edit may make, reported in "
                 "allowed_changes: " + ", ".join(edit_options.ALLOWABLE))
    if cmd in ("plan", "judge", "fix", "polish"):
        cli_config.add_argument(parser)
    if cmd in ("fix", "polish", "submit"):
        parser.add_argument(
            "--explain", nargs="?", const="json", choices=("json", "text"), default=None,
            help="report each changed sentence and the findings it cleared: json adds "
                 "`changes` to the result, text prints a readable report")


def edit_kwargs(args):
    """Keyword options for host_edit.edit_plan or editing.run_edit. Empty when
    no option is set, so the call is the same as before these options existed."""
    allow = edit_options.parse_allow(getattr(args, "allow_change", None))
    return {"allow_change": allow} if allow else {}


def render(args, result, original):
    """The text to print for an edit result: the JSON, or the change report."""
    mode = getattr(args, "explain", None)
    report = changes.for_result(original, result) if mode else None
    if report is not None and mode == "text":
        return changes.format_report(report, getattr(args, "file", ""))
    if report is not None:
        result["changes"] = report
    return json.dumps(result, ensure_ascii=False, indent=2)
