"""Command-line entrypoint."""

from __future__ import annotations

import argparse
import json
import os
import sys

import yaml

from .agent import run_task
from .sinks import emit
from .task import Task, load_all


def _defaults(path: str = "config.yaml") -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return (yaml.safe_load(fh) or {}).get("defaults", {})


def cmd_list(args) -> int:
    tasks = load_all(args.tasks_dir)
    if not tasks:
        print(f"No tasks found in {args.tasks_dir}/")
        return 0
    width = max(len(n) for n in tasks)
    for name, t in tasks.items():
        sched = f"  [{t.schedule}]" if t.schedule else ""
        missing = t.missing_secrets()
        warn = f"  !! missing secrets: {', '.join(missing)}" if missing else ""
        print(f"{name.ljust(width)}  {t.description or t.goal[:60]}{sched}{warn}")
    return 0


def cmd_validate(args) -> int:
    ok = True
    tasks_dir = args.tasks_dir
    for fn in sorted(os.listdir(tasks_dir)):
        if not fn.endswith((".yaml", ".yml")):
            continue
        path = os.path.join(tasks_dir, fn)
        try:
            t = Task.from_file(path)
            missing = t.missing_secrets()
            note = f" (secrets not set: {', '.join(missing)})" if missing else ""
            print(f"ok    {fn}{note}")
        except Exception as e:
            ok = False
            print(f"FAIL  {fn}: {e}")
    return 0 if ok else 1


def cmd_run(args) -> int:
    tasks = load_all(args.tasks_dir)
    if args.task not in tasks:
        print(f"No task named '{args.task}'. Available: {', '.join(tasks) or '(none)'}")
        return 2

    task = tasks[args.task]
    defaults = _defaults(args.config)

    if args.headed:
        task.headless = False
    if args.model:
        task.model = args.model
    if args.max_steps:
        task.max_steps = args.max_steps

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set.")
        return 2

    print(f"running: {task.name}")
    result = run_task(task, defaults, verbose=not args.quiet)
    payload = result.to_dict()

    sinks = task.sinks or [{"type": "file"}]
    if args.stdout:
        sinks = [{"type": "stdout"}]
    delivered = emit(payload, sinks)

    print(
        f"\n{result.status}: {result.summary or result.reason}\n"
        f"{result.steps} steps · {result.elapsed_seconds:.0f}s · ${result.cost_usd:.4f}"
    )
    for k, v in delivered.items():
        print(f"  -> {k}: {v}")

    return 0 if result.status == "completed" else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="webagent", description="Scheduled browser agent")
    p.add_argument("--tasks-dir", default="tasks")
    p.add_argument("--config", default="config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list available tasks").set_defaults(func=cmd_list)
    sub.add_parser("validate", help="check every task file parses").set_defaults(func=cmd_validate)

    r = sub.add_parser("run", help="run one task")
    r.add_argument("task")
    r.add_argument("--headed", action="store_true", help="show the browser (debugging)")
    r.add_argument("--model", help="override the model for this run")
    r.add_argument("--max-steps", type=int)
    r.add_argument("--stdout", action="store_true", help="print JSON instead of using sinks")
    r.add_argument("--quiet", action="store_true")
    r.set_defaults(func=cmd_run)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
