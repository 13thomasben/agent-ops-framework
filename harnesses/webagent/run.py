#!/usr/bin/env python3
"""Convenience entrypoint: `python run.py run <task>`

Paths resolve against this file's directory rather than the caller's, so the
skill can be invoked from the repo root and still find `tasks/` and
`config.yaml` — and, more importantly, write `runs/` and `state/` inside this
folder, where the local .gitignore keeps scraped data and live session cookies
out of the repo.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from webagent.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
