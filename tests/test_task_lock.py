import json
import os
from pathlib import Path

import pytest

from sdd.task_lock import (
    StaleTaskLockError, TaskLockError, acquire_task_lock, is_task_locked, release_task_lock,
)


def test_lock_lifecycle_and_independent_tasks(tmp_path: Path) -> None:
    a = acquire_task_lock("a", tmp_path)
    b = acquire_task_lock("b", tmp_path)
    assert a != b and is_task_locked("a", tmp_path) and is_task_locked("b", tmp_path)
    with pytest.raises(TaskLockError, match="already locked"):
        acquire_task_lock("a", tmp_path)
    release_task_lock("a", tmp_path)
    assert not is_task_locked("a", tmp_path) and is_task_locked("b", tmp_path)


def test_stale_lock_requires_audited_explicit_cleanup(tmp_path: Path) -> None:
    path = tmp_path / "old.lock"
    path.write_text(json.dumps({"task_id": "old", "pid": 2_000_000_000,
                                "created_at": "2020-01-01T00:00:00Z"}))
    assert not is_task_locked("old", tmp_path)
    with pytest.raises(StaleTaskLockError, match="explicitly"):
        acquire_task_lock("old", tmp_path)
    release_task_lock("old", tmp_path)
    assert not path.exists()
    assert '"task_id": "old"' in (tmp_path / "stale-locks.log").read_text()


@pytest.mark.parametrize("task_id", ["", "../x", "/absolute", "a/b"])
def test_invalid_task_id_rejected(tmp_path: Path, task_id: str) -> None:
    with pytest.raises(ValueError):
        acquire_task_lock(task_id, tmp_path)
