"""Strict atomic local registry of M4 TaskRecord values."""

from __future__ import annotations

from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from sdd._persistence import atomic_yaml, load_mapping, validate_run_id
from sdd.models import TaskRecord

TASK_STATUSES = {
    "queued", "starting", "running", "awaiting_human", "blocked",
    "completed", "failed", "cancelled",
}
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
ALLOWED_TRANSITIONS = {
    "queued": {"starting", "cancelled"},
    "starting": {"running", "failed"},
    "running": {"awaiting_human", "blocked", "completed", "failed", "cancelled"},
    "awaiting_human": {"queued", "cancelled"},
    "blocked": {"queued", "cancelled"},
    "completed": set(), "failed": set(), "cancelled": set(),
}
_FIELD_NAMES = {item.name for item in fields(TaskRecord)}


class TaskRegistryError(RuntimeError):
    pass


def validate_status_transition(previous: str, current: str) -> None:
    if previous not in TASK_STATUSES or current not in TASK_STATUSES:
        raise TaskRegistryError("unknown task status")
    if previous != current and current not in ALLOWED_TRANSITIONS[previous]:
        raise TaskRegistryError(f"invalid task status transition: {previous} -> {current}")


def _validate_task(task: TaskRecord) -> None:
    validate_run_id(task.task_id)
    validate_run_id(task.run_id)
    for name in ("repository", "worktree_path", "branch", "base_commit", "created_at"):
        if not isinstance(getattr(task, name), str) or not getattr(task, name):
            raise TaskRegistryError(f"field {name} must be a non-empty string")
    if task.status not in TASK_STATUSES:
        raise TaskRegistryError(f"unknown task status: {task.status}")
    for name in ("started_at", "finished_at", "current_node", "error"):
        if getattr(task, name) is not None and not isinstance(getattr(task, name), str):
            raise TaskRegistryError(f"field {name} must be a string or null")
    if task.pid is not None and (not isinstance(task.pid, int) or isinstance(task.pid, bool) or task.pid < 1):
        raise TaskRegistryError("field pid must be a positive integer or null")
    if not isinstance(task.cleanup_allowed, bool):
        raise TaskRegistryError("field cleanup_allowed must be bool")


def _from_mapping(value: Any) -> TaskRecord:
    if not isinstance(value, dict):
        raise TaskRegistryError("each registry task must be an object")
    unknown = sorted(set(value) - _FIELD_NAMES)
    missing = sorted(_FIELD_NAMES - set(value))
    if unknown or missing:
        detail = []
        if unknown:
            detail.append("unknown fields: " + ", ".join(unknown))
        if missing:
            detail.append("missing fields: " + ", ".join(missing))
        raise TaskRegistryError("; ".join(detail))
    try:
        task = TaskRecord(**value)
        _validate_task(task)
    except (TypeError, ValueError) as error:
        raise TaskRegistryError(f"invalid TaskRecord: {error}") from error
    return task


class TaskRegistry:
    def __init__(self, path: str | Path = "runs/tasks.yaml") -> None:
        self.path = Path(path)

    def _load(self) -> list[TaskRecord]:
        if not self.path.exists():
            return []
        try:
            data = load_mapping(self.path)
        except (ValueError, OSError) as error:
            raise TaskRegistryError(f"cannot load task registry: {error}") from error
        if set(data) != {"tasks"} or not isinstance(data["tasks"], list):
            raise TaskRegistryError("registry must contain exactly one tasks list")
        tasks = [_from_mapping(item) for item in data["tasks"]]
        self._validate_unique(tasks)
        return tasks

    @staticmethod
    def _validate_unique(tasks: list[TaskRecord]) -> None:
        for attribute in ("task_id", "run_id", "worktree_path", "branch"):
            values = [getattr(task, attribute) for task in tasks]
            if len(values) != len(set(values)):
                raise TaskRegistryError(f"duplicate {attribute}")

    def _write(self, tasks: list[TaskRecord]) -> None:
        self._validate_unique(tasks)
        atomic_yaml(self.path, {"tasks": [asdict(task) for task in tasks]})

    def register_task(self, task: TaskRecord) -> None:
        _validate_task(task)
        tasks = self._load()
        tasks.append(_from_mapping(asdict(task)))
        self._write(tasks)

    def get_task(self, task_id: str) -> TaskRecord:
        validate_run_id(task_id)
        for task in self._load():
            if task.task_id == task_id:
                return task
        raise KeyError(task_id)

    def list_tasks(self) -> list[TaskRecord]:
        return self._load()

    def update_task(self, task: TaskRecord) -> None:
        _validate_task(task)
        tasks = self._load()
        for index, previous in enumerate(tasks):
            if previous.task_id == task.task_id:
                validate_status_transition(previous.status, task.status)
                tasks[index] = _from_mapping(asdict(task))
                self._write(tasks)
                return
        raise KeyError(task.task_id)

    def remove_task(self, task_id: str) -> None:
        task = self.get_task(task_id)
        tasks = [item for item in self._load() if item.task_id != task.task_id]
        self._write(tasks)


_default = TaskRegistry()

def register_task(task: TaskRecord) -> None: _default.register_task(task)
def get_task(task_id: str) -> TaskRecord: return _default.get_task(task_id)
def list_tasks() -> list[TaskRecord]: return _default.list_tasks()
def update_task(task: TaskRecord) -> None: _default.update_task(task)
def remove_task(task_id: str) -> None: _default.remove_task(task_id)
