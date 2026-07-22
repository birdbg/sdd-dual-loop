"""Process-aware local lock files for M4 tasks."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from sdd._persistence import validate_run_id


class TaskLockError(RuntimeError):
    pass


class StaleTaskLockError(TaskLockError):
    pass


def _path(task_id: str, locks_root: str | Path) -> Path:
    validate_run_id(task_id)
    return Path(locks_root) / f"{task_id}.lock"


def _read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TaskLockError(f"invalid task lock {path}: {error}") from error
    if set(value) != {"task_id", "pid", "created_at"}:
        raise TaskLockError("task lock has invalid fields")
    if not isinstance(value["task_id"], str) or not isinstance(value["pid"], int) or not isinstance(value["created_at"], str):
        raise TaskLockError("task lock has invalid field types")
    return value


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire_task_lock(task_id: str, locks_root: str | Path) -> Path:
    path = _path(task_id, locks_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"task_id": task_id, "pid": os.getpid(), "created_at": datetime.now(timezone.utc).isoformat()}
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        existing = _read(path)
        if not _alive(existing["pid"]):
            raise StaleTaskLockError(
                f"stale lock for {task_id}; call release_task_lock explicitly to audit cleanup"
            ) from error
        raise TaskLockError(f"task {task_id} is already locked") from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def release_task_lock(task_id: str, locks_root: str | Path) -> None:
    path = _path(task_id, locks_root)
    if not path.exists():
        return
    value = _read(path)
    if value["task_id"] != task_id:
        raise TaskLockError("lock task_id does not match filename")
    stale = not _alive(value["pid"])
    if value["pid"] != os.getpid() and not stale:
        raise TaskLockError("cannot release a lock owned by a live process")
    if stale:
        audit = path.parent / "stale-locks.log"
        with audit.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({
                "task_id": task_id, "stale_pid": value["pid"],
                "cleaned_at": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False) + "\n")
    path.unlink()


def is_task_locked(task_id: str, locks_root: str | Path) -> bool:
    path = _path(task_id, locks_root)
    if not path.exists():
        return False
    value = _read(path)
    return _alive(value["pid"])
