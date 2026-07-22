from pathlib import Path
import subprocess

from sdd.models import Plan, Spec, Task, VerifyResult
from sdd.scheduler import LocalScheduler
from sdd.intention_loop.archive import archive_run
from sdd.scheduler import SchedulerError
from sdd.task_lock import acquire_task_lock, release_task_lock
import pytest


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, text=True,
                          capture_output=True).stdout.strip()


def fastapi_repo(tmp_path: Path) -> Path:
    root = tmp_path / "fastapi-source"
    (root / "app").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "app" / "__init__.py").write_text("")
    (root / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
    (root / "tests" / "test_app.py").write_text("def test_base(): assert True\n")
    (root / "pyproject.toml").write_text(
        "[project]\nname='demo'\nversion='1'\ndependencies=['fastapi']\n"
        "[project.optional-dependencies]\ntest=['pytest']\n"
    )
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    return root


def test_three_tasks_keep_worktrees_and_m3_state_isolated(tmp_path: Path) -> None:
    repository = fastapi_repo(tmp_path)
    main_branch = git(repository, "branch", "--show-current")
    main_content = (repository / "app" / "main.py").read_text()
    scheduler = LocalScheduler(tmp_path / "runs", tmp_path / "trees", 2)
    for name in ("customer-search", "health", "date-format"):
        scheduler.submit_task(repository, name, run_id=f"run-{name}")

    assert [item.task_id for item in scheduler.start_ready_tasks()] == ["customer-search", "health"]
    assert scheduler.get_task("date-format").status == "queued"
    a = scheduler.get_task("customer-search")
    b = scheduler.get_task("health")
    assert a.worktree_path != b.worktree_path and a.branch != b.branch

    context_a = scheduler.prepare_run_context("customer-search", "客户名称模糊搜索")
    context_a.spec = Spec(["search customers"], ["matching undefined"])
    context_a.plan = Plan([Task("search", "search", ["app/main.py"])])
    context_a.verify_result = VerifyResult(False, ["needs human rule"])
    runner_a = scheduler.runner_for(a)
    runner_a.record_spec(context_a)
    runner_a.record_plan(context_a)
    runner_a.record_verify(context_a)
    context_a.status = "awaiting_human"
    context_a.current_node = "change_spec"
    runner_a.persist(context_a)
    scheduler.sync_from_context("customer-search", context_a)

    scheduler.start_ready_tasks()
    assert scheduler.get_task("date-format").status == "running"
    c = scheduler.get_task("date-format")
    context_c = scheduler.prepare_run_context("date-format", "修复日期格式")
    assert context_c.run_id != context_a.run_id

    context_b = scheduler.prepare_run_context("health", "增加 GET /health")
    context_b.status = "failed"
    context_b.current_node = "testing"
    scheduler.runner_for(b).persist(context_b)
    scheduler.sync_from_context("health", context_b)
    assert scheduler.get_task("date-format").status == "running"

    runner_a.apply_spec_change(context_a, "define fuzzy search", ["case-insensitive contains"], "owner")
    scheduler.resume_task("customer-search")
    assert scheduler.get_task("customer-search").status == "queued"
    context_c.status = "completed"
    context_c.current_node = "archive"
    scheduler.runner_for(c).persist(context_c)
    scheduler.sync_from_context("date-format", context_c)
    scheduler.start_ready_tasks()
    resumed = scheduler.get_task("customer-search")
    assert resumed.status == "running"
    restored = scheduler.runner_for(resumed).resume(resumed.run_id, resumed.worktree_path)
    assert restored.spec_version == 2 and restored.current_node == "brainstorming"

    for task in (a, b, c):
        run = scheduler.runs_root / task.run_id
        assert (run / "checkpoint.yaml").is_file()
        assert (run / "run-context.yaml").is_file()
    assert (scheduler.runs_root / a.run_id / "spec-r2.yaml").is_file()
    assert not (scheduler.runs_root / b.run_id / "spec-r2.yaml").exists()
    assert git(repository, "branch", "--show-current") == main_branch
    assert (repository / "app" / "main.py").read_text() == main_content
    assert git(repository, "status", "--porcelain") == ""


def test_terminal_cleanup_is_safe_and_retains_branch_and_archive(tmp_path: Path) -> None:
    repository = fastapi_repo(tmp_path)
    scheduler = LocalScheduler(tmp_path / "runs", tmp_path / "trees", 2)
    scheduler.submit_task(repository, "done", run_id="run-done")
    scheduler.submit_task(repository, "other", run_id="run-other")
    scheduler.start_ready_tasks()
    done = scheduler.get_task("done")
    context = scheduler.prepare_run_context("done", "health")
    context.status = "completed"
    context.current_node = "archive"
    context.resume_allowed = False
    archive_run(context, scheduler.runs_root)
    scheduler.sync_from_context("done", context)

    assert Path(done.worktree_path).exists()
    scheduler.cleanup_task("done")
    assert not Path(done.worktree_path).exists()
    assert git(repository, "show-ref", "--verify", "refs/heads/sdd/done")
    assert (scheduler.runs_root / done.run_id / "archive.md").exists()
    assert Path(scheduler.get_task("other").worktree_path).exists()


def test_cleanup_guards_state_archive_changes_and_lock(tmp_path: Path) -> None:
    repository = fastapi_repo(tmp_path)
    scheduler = LocalScheduler(tmp_path / "runs", tmp_path / "trees", 1)
    scheduler.submit_task(repository, "guard", run_id="run-guard")
    scheduler.start_ready_tasks()
    with pytest.raises(SchedulerError, match="terminal"):
        scheduler.cleanup_task("guard")
    task = scheduler.get_task("guard")
    context = scheduler.prepare_run_context("guard", "date")
    context.status = "failed"
    context.current_node = "testing"
    scheduler.runner_for(task).persist(context)
    scheduler.sync_from_context("guard", context)
    with pytest.raises(SchedulerError, match="Archive"):
        scheduler.cleanup_task("guard")
    archive_run(context, scheduler.runs_root)
    acquire_task_lock("guard", scheduler.locks_root)
    with pytest.raises(SchedulerError, match="lock"):
        scheduler.cleanup_task("guard")
    release_task_lock("guard", scheduler.locks_root)
    (Path(task.worktree_path) / "local.txt").write_text("not archived")
    with pytest.raises(SchedulerError, match="unarchived"):
        scheduler.cleanup_task("guard")
