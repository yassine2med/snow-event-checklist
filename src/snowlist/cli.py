"""Command line entry for the snow event checklist."""

from __future__ import annotations

import argparse
import json
import sys

from .core import ChecklistError, blocked_by, classify, load_checklist, parse_time, timeline, validate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="snowlist", description="Snow event checklist with timers")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="check the checklist file").add_argument("file")
    plan = sub.add_parser("plan", help="print the timeline for an event start")
    plan.add_argument("file")
    plan.add_argument("--start", required=True, help='event start, for example "2026-01-24 18:00"')
    status = sub.add_parser("status", help="what is done, overdue or due soon right now")
    status.add_argument("file")
    status.add_argument("--start", required=True)
    status.add_argument("--now", required=True, help='current time, same format as --start')
    status.add_argument("--done", default="", help="comma separated ids already finished")
    status.add_argument("--done-file", help="JSON file holding a list of finished ids")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Return 0 when fine, 1 for problems or overdue tasks, 2 for unreadable input."""
    args = build_parser().parse_args(argv)
    try:
        event, tasks = load_checklist(args.file)
    except FileNotFoundError:
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2
    except ChecklistError as exc:
        print(f"Bad input: {exc}", file=sys.stderr)
        return 2
    if args.command == "validate":
        problems = validate(tasks)
        for p in problems:
            print(p)
        print(f"{len(tasks)} tasks checked, {len(problems)} problem(s)")
        return 1 if problems else 0
    problems = validate(tasks)
    if problems:
        print(f"Checklist has {len(problems)} problem(s); run validate first", file=sys.stderr)
        return 2
    try:
        start = parse_time(args.start)
        now = parse_time(args.now) if args.command == "status" else None
        done: set[str] = set()
        if args.command == "status":
            done = {d.strip() for d in args.done.split(",") if d.strip()}
            if args.done_file:
                with open(args.done_file, encoding="utf-8") as fh:
                    done |= set(json.load(fh))
    except (ChecklistError, OSError, json.JSONDecodeError, TypeError) as exc:
        print(f"Bad input: {exc}", file=sys.stderr)
        return 2
    print(f"{event}, event start {start:%Y-%m-%d %H:%M}")
    if args.command == "plan":
        for due, task in timeline(tasks, start):
            print(f"{due:%a %m-%d %H:%M}  {f'T{task.due_hours:+g}h':<7}{task.owner:<21}{task.title}")
        print(f"{len(tasks)} tasks")
        return 0
    unknown = sorted(done - {t.id for t in tasks})
    if unknown:
        print(f"Bad input: unknown id(s) in done list: {', '.join(unknown)}", file=sys.stderr)
        return 2
    overdue = 0
    for due, task in timeline(tasks, start):
        state = classify(task, start, now, done)
        overdue += state == "OVERDUE"
        waiting = blocked_by(task, done)
        note = f"  (waiting on {', '.join(waiting)})" if waiting and state != "DONE" else ""
        print(f"{state:<9} {due:%a %m-%d %H:%M}  {task.id:<11} {task.owner:<20}{note}")
    print(f"{len(done)} done, {overdue} overdue, now {now:%Y-%m-%d %H:%M}")
    return 1 if overdue else 0


if __name__ == "__main__":
    sys.exit(main())
