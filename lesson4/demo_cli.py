"""A tiny CLI so the notebook can demonstrate process-level interfaces."""

from __future__ import annotations

import argparse
import json

from tool_demo import get_weather


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lesson4", description="Lesson 4 demo CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    greet = subparsers.add_parser("greet", help="print a greeting")
    greet.add_argument("--name", required=True)

    weather = subparsers.add_parser("weather", help="print sample weather as JSON")
    weather.add_argument("--city", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "greet":
        print(f"Hello, {args.name}!")
    elif args.command == "weather":
        print(json.dumps(get_weather(args.city), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

