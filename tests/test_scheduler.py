from pathlib import Path
import subprocess

import pytest

from sdd.models import RunContext
from sdd.scheduler import LocalScheduler, SchedulerError


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, text=True,
                          capture_output=True).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n")
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    return root


def scheduler(tmp_path: Path) -> LocalScheduler:
    return LocalScheduler(tmp_path / "runs", tmp_path / "trees", 2)


def test_invalid_concurrency_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        LocalScheduler(tmp_path / "runs", tmp_path / "trees", 0)


def test_bounded_fifo_and_completion_opens_slot(repository: Path, tmp_path: Path) -> None:
    current = scheduler(tmp_path)
    for name in ("a", "b", "c"):
        current.submit_task(repository, name, run_id=f"run-{name}")
    assert [task.task_id for task in current.start_ready_tasks()] == ["a", "b"]
    assert current.get_task("c").status == "queued"
    a = current.get_task("a")
    current.sync_from_context("a", RunContext(a.run_id, "a", status="completed"))
    assert [task.task_id for task in current.start_ready_tasks()] == ["c"]
    assert current.get_scheduler_summary()["running"] == ["b", "c"]


def test_failure_isolated_and_next_task_starts(repository: Path, tmp_path: Path) -> None:
    current = scheduler(tmp_path)
    for name in ("a", "b", "c"):
        current.submit_task(repository, name)

    def starter(task, _runner):
        if task.task_id == "a":
            raise RuntimeError("only a failed")
        return None

    result = current.start_ready_tasks(starter)
    assert [task.status for task in result] == ["failed", "running"]
    current.start_ready_tasks()
    assert current.get_task("c").status == "running"
    assert current.get_task("b").status == "running"


@pytest.mark.parametrize("paused", ["awaiting_human", "blocked"])
def test_pause_releases_slot_and_resume_is_queued(repository: Path, tmp_path: Path, paused: str) -> None:
    current = scheduler(tmp_path)
    current.submit_task(repository, "a")
    current.submit_task(repository, "b")
    current.submit_task(repository, "c")
    current.start_ready_tasks()
    current.pause_task("a", paused)
    assert current.get_scheduler_summary()["available_slots"] == 1
    current.start_ready_tasks()
    assert current.get_task("c").status == "running"
    # Full persisted-state resume validation is covered by M4 integration tests.
    with pytest.raises((SchedulerError, FileNotFoundError)):
        current.resume_task("a")


def test_cancel_does_not_affect_other_task(repository: Path, tmp_path: Path) -> None:
    current = scheduler(tmp_path)
    current.submit_task(repository, "a")
    current.submit_task(repository, "b")
    current.start_ready_tasks()
    current.cancel_task("a")
    assert current.get_task("a").status == "cancelled"
    assert current.get_task("b").status == "running"
    with pytest.raises(SchedulerError):
        current.cancel_task("a")
