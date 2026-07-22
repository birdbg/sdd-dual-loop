"""Bounded FIFO state-machine scheduler for local isolated M3 tasks."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Callable

from sdd.checkpoint import load_checkpoint
from sdd.m3 import M3Runner
from sdd.models import RunContext, TaskRecord
from sdd.state_store import load_run_context
from sdd.task_lock import acquire_task_lock, is_task_locked, release_task_lock
from sdd.task_registry import TERMINAL_STATUSES, TaskRegistry
from sdd.worktree import create_task_worktree, validate_task_worktree


class SchedulerError(RuntimeError):
    pass


Starter = Callable[[TaskRecord, M3Runner], RunContext | None]


class LocalScheduler:
    """Persist task facts; derive queue and slot state on every operation."""

    def __init__(
        self,
        runs_root: str | Path = "runs",
        worktrees_root: str | Path = ".sdd-worktrees",
        max_concurrency: int = 2,
    ) -> None:
        if not isinstance(max_concurrency, int) or isinstance(max_concurrency, bool) or max_concurrency < 1:
            raise ValueError("max_concurrency must be greater than 0")
        self.runs_root = Path(runs_root).expanduser().resolve()
        self.worktrees_root = Path(worktrees_root).expanduser().resolve()
        self.max_concurrency = max_concurrency
        self.registry = TaskRegistry(self.runs_root / "tasks.yaml")
        self.locks_root = self.runs_root / "locks"

    def submit_task(
        self,
        repository: str | Path,
        task_id: str,
        *,
        run_id: str | None = None,
        base_ref: str = "main",
    ) -> TaskRecord:
        existing = self.registry.list_tasks()
        if any(item.task_id == task_id for item in existing):
            raise SchedulerError(f"task_id already registered: {task_id}")
        if run_id is not None and any(item.run_id == run_id for item in existing):
            raise SchedulerError(f"run_id already registered: {run_id}")
        task = create_task_worktree(repository, task_id, self.worktrees_root, base_ref)
        if run_id is not None:
            task.run_id = run_id
        try:
            self.registry.register_task(task)
        except BaseException:
            # Registration is attempted only after all predictable uniqueness checks.
            # Leave no Worktree if persistence unexpectedly fails.
            from sdd.worktree import remove_task_worktree
            remove_task_worktree(task)
            raise
        return self.registry.get_task(task_id)

    def list_tasks(self) -> list[TaskRecord]:
        return self.registry.list_tasks()

    def get_task(self, task_id: str) -> TaskRecord:
        return self.registry.get_task(task_id)

    def runner_for(self, task: TaskRecord) -> M3Runner:
        validate_task_worktree(task)
        return M3Runner(self.runs_root)

    def start_ready_tasks(self, starter: Starter | None = None) -> list[TaskRecord]:
        tasks = self.registry.list_tasks()
        occupied = sum(task.status in {"starting", "running"} for task in tasks)
        ready = [task for task in tasks if task.status == "queued"]
        # YAML list order is registration order; created_at makes the rule explicit.
        indexed = {task.task_id: index for index, task in enumerate(tasks)}
        ready.sort(key=lambda task: (task.created_at, indexed[task.task_id]))
        started: list[TaskRecord] = []
        for task in ready[:max(0, self.max_concurrency - occupied)]:
            task.status = "starting"
            if task.started_at is None:
                task.started_at = _now()
            self.registry.update_task(task)
            try:
                validate_task_worktree(task)
                acquire_task_lock(task.task_id, self.locks_root)
                task.status = "running"
                task.pid = os.getpid()
                self.registry.update_task(task)
                if starter is not None:
                    context = starter(task, self.runner_for(task))
                    if context is not None:
                        self.sync_from_context(task.task_id, context)
                started.append(self.registry.get_task(task.task_id))
            except BaseException as error:
                current = self.registry.get_task(task.task_id)
                if current.status in {"starting", "running"}:
                    current.status = "failed"
                    current.error = str(error)
                    current.finished_at = _now()
                    current.cleanup_allowed = True
                    self.registry.update_task(current)
                release_task_lock(task.task_id, self.locks_root)
                # Failure isolation is intentional: continue assigning other slots.
                started.append(self.registry.get_task(task.task_id))
        return started

    def sync_from_context(self, task_id: str, context: RunContext) -> TaskRecord:
        task = self.registry.get_task(task_id)
        if context.run_id != task.run_id:
            raise SchedulerError("RunContext run_id does not match TaskRecord")
        mapping = {
            "running": "running", "awaiting_human": "awaiting_human",
            "blocked": "blocked", "completed": "completed", "failed": "failed",
        }
        if context.status not in mapping:
            raise SchedulerError(f"RunContext status cannot update a task: {context.status}")
        target = mapping[context.status]
        task.status = target
        task.current_node = context.current_node
        if target in {"awaiting_human", "blocked"} | TERMINAL_STATUSES:
            task.pid = None
            release_task_lock(task_id, self.locks_root)
        if target in TERMINAL_STATUSES:
            task.finished_at = _now()
            task.cleanup_allowed = True
        self.registry.update_task(task)
        return self.registry.get_task(task_id)

    def pause_task(self, task_id: str, status: str | None = None) -> TaskRecord:
        task = self.registry.get_task(task_id)
        if task.status != "running":
            raise SchedulerError("pause_task only accepts a running task")
        if status is None:
            try:
                context = load_run_context(task.run_id, self.runs_root)
            except (OSError, ValueError) as error:
                raise SchedulerError(f"cannot read RunContext for pause: {error}") from error
            status = context.status
            task.current_node = context.current_node
        if status not in {"awaiting_human", "blocked"}:
            raise SchedulerError("pause result must reflect awaiting_human or blocked RunContext")
        task.status = status
        task.pid = None
        self.registry.update_task(task)
        release_task_lock(task_id, self.locks_root)
        return self.registry.get_task(task_id)

    def resume_task(self, task_id: str) -> TaskRecord:
        task = self.registry.get_task(task_id)
        if task.status not in {"awaiting_human", "blocked"}:
            raise SchedulerError("resume_task only accepts awaiting_human or blocked tasks")
        validate_task_worktree(task)
        if is_task_locked(task_id, self.locks_root):
            raise SchedulerError("task is still locked")
        checkpoint = load_checkpoint(task.run_id, self.runs_root)
        context = load_run_context(task.run_id, self.runs_root)
        if checkpoint.run_id != task.run_id or context.run_id != task.run_id:
            raise SchedulerError("persisted run_id does not match TaskRecord")
        if checkpoint.status != task.status or context.status != task.status:
            raise SchedulerError("persisted status does not match TaskRecord")
        self.runner_for(task).resume(task.run_id, task.worktree_path)
        task.status = "queued"
        task.pid = None
        self.registry.update_task(task)
        return self.registry.get_task(task_id)

    def cancel_task(self, task_id: str) -> TaskRecord:
        task = self.registry.get_task(task_id)
        if task.status not in {"queued", "running", "awaiting_human", "blocked"}:
            raise SchedulerError("task status cannot be cancelled")
        was_running = task.status == "running"
        task.status = "cancelled"
        task.pid = None
        task.finished_at = _now()
        task.cleanup_allowed = True
        self.registry.update_task(task)
        if was_running:
            release_task_lock(task_id, self.locks_root)
        return self.registry.get_task(task_id)

    def get_scheduler_summary(self) -> dict[str, object]:
        tasks = self.registry.list_tasks()
        occupied = sum(task.status in {"starting", "running"} for task in tasks)
        return {
            "max_concurrency": self.max_concurrency,
            "occupied_slots": occupied,
            "available_slots": self.max_concurrency - occupied,
            "queued": [task.task_id for task in tasks if task.status == "queued"],
            "running": [task.task_id for task in tasks if task.status == "running"],
            "counts": {status: sum(task.status == status for task in tasks)
                       for status in ("queued", "starting", "running", "awaiting_human", "blocked", "completed", "failed", "cancelled")},
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def submit_task(scheduler: LocalScheduler, *args: object, **kwargs: object) -> TaskRecord:
    return scheduler.submit_task(*args, **kwargs)
def start_ready_tasks(scheduler: LocalScheduler, starter: Starter | None = None) -> list[TaskRecord]:
    return scheduler.start_ready_tasks(starter)
def pause_task(scheduler: LocalScheduler, task_id: str, status: str | None = None) -> TaskRecord:
    return scheduler.pause_task(task_id, status)
def resume_task(scheduler: LocalScheduler, task_id: str) -> TaskRecord:
    return scheduler.resume_task(task_id)
def cancel_task(scheduler: LocalScheduler, task_id: str) -> TaskRecord:
    return scheduler.cancel_task(task_id)
def get_scheduler_summary(scheduler: LocalScheduler) -> dict[str, object]:
    return scheduler.get_scheduler_summary()
