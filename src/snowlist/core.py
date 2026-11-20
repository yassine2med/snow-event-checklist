"""A snow event checklist as data: timed tasks, owners and dependencies."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

TIME_FORMAT = "%Y-%m-%d %H:%M"


class ChecklistError(ValueError):
    """Raised when the checklist file cannot be read."""


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    owner: str
    due_hours: float
    depends_on: tuple[str, ...] = ()

    def due(self, start: datetime) -> datetime:
        return start + timedelta(hours=self.due_hours)


def parse_time(text: str) -> datetime:
    try:
        return datetime.strptime(text, TIME_FORMAT)
    except ValueError as exc:
        raise ChecklistError(f"time '{text}' must look like 2026-01-24 18:00") from exc


def load_checklist(path: str) -> tuple[str, list[Task]]:
    """Read a checklist JSON file into (event name, tasks). Structure only; see validate()."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ChecklistError(f"not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise ChecklistError("expected an object with a 'tasks' list")
    tasks = []
    for n, raw in enumerate(data["tasks"], start=1):
        if not isinstance(raw, dict) or "id" not in raw or "due_hours" not in raw:
            raise ChecklistError(f"task {n}: needs at least 'id' and 'due_hours'")
        if not isinstance(raw["due_hours"], (int, float)) or isinstance(raw["due_hours"], bool):
            raise ChecklistError(f"task {n}: 'due_hours' must be a number")
        tasks.append(Task(str(raw["id"]), str(raw.get("title", "")), str(raw.get("owner", "")),
                          float(raw["due_hours"]), tuple(raw.get("depends_on", []))))
    return str(data.get("event", "Event")), tasks


def validate(tasks: list[Task]) -> list[str]:
    """Return a list of problems: empty fields, duplicate ids, unknown or circular dependencies, bad ordering."""
    problems = []
    ids = [t.id for t in tasks]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"duplicate id '{dup}'")
    by_id = {t.id: t for t in tasks}
    for t in tasks:
        if not t.title.strip():
            problems.append(f"{t.id}: title is empty")
        if not t.owner.strip():
            problems.append(f"{t.id}: owner is empty")
        for dep in t.depends_on:
            if dep not in by_id:
                problems.append(f"{t.id}: depends on unknown task '{dep}'")
            elif by_id[dep].due_hours > t.due_hours:
                problems.append(f"{t.id}: due before its dependency '{dep}'")
    for cycle in _cycles(by_id):
        problems.append("circular dependency: " + " -> ".join(cycle))
    return problems


def _cycles(by_id: dict[str, Task]) -> list[list[str]]:
    found, state = [], {}

    def visit(node: str, path: list[str]) -> None:
        state[node] = 1
        for dep in by_id[node].depends_on:
            if dep not in by_id:
                continue
            if state.get(dep) == 1:
                found.append(path[path.index(dep):] + [dep] if dep in path else [node, dep])
            elif dep not in state:
                visit(dep, path + [dep])
        state[node] = 2

    for task_id in by_id:
        if task_id not in state:
            visit(task_id, [task_id])
    return found


def timeline(tasks: list[Task], start: datetime) -> list[tuple[datetime, Task]]:
    return sorted(((t.due(start), t) for t in tasks), key=lambda p: (p[0], p[1].id))


def classify(task: Task, start: datetime, now: datetime, done: set[str], soon_hours: float = 2) -> str:
    """DONE, OVERDUE, DUE SOON (within soon_hours) or UPCOMING."""
    if task.id in done:
        return "DONE"
    due = task.due(start)
    if due < now:
        return "OVERDUE"
    if due - now <= timedelta(hours=soon_hours):
        return "DUE SOON"
    return "UPCOMING"


def blocked_by(task: Task, done: set[str]) -> list[str]:
    """Dependencies of a task that are not yet done."""
    return [d for d in task.depends_on if d not in done]
