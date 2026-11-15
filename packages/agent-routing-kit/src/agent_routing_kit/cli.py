import argparse
import json

from .budget import estimate_context
from .routing import route_task


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Route a task to public-safe capabilities.")
    parser.add_argument("task", help="Task text to route.")
    parser.add_argument("--include-private", action="store_true", help="Include private/restricted labels.")
    parser.add_argument("--max-results", type=int, default=3, help="Maximum route matches.")
    parser.add_argument("--max-context", type=int, default=8000, help="Context budget for task text.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    route = route_task(
        args.task,
        include_private=args.include_private,
        max_results=args.max_results,
    )
    budget = estimate_context(args.task, max_tokens=args.max_context)

    if args.json:
        print(json.dumps({"route": route.to_dict(), "context": budget.to_dict()}, indent=2))
    else:
        print(route.to_markdown())
        print()
        print(f"Context: {budget.estimated_tokens}/{budget.max_tokens} tokens ({budget.status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
