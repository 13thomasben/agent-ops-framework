"""webagent — a task-driven browser agent."""

__version__ = "0.1.0"

from .task import Task, load_all
from .agent import run_task, RunResult

__all__ = ["Task", "load_all", "run_task", "RunResult"]
