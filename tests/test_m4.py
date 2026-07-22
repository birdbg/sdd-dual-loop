from pathlib import Path
import subprocess

from sdd.models import Plan, Spec, Task, VerifyResult
from sdd.scheduler import LocalScheduler
from sdd.intention_loop.archive import archive_run
from sdd.scheduler import SchedulerError
from sdd.task_lock import acquire_task_lock, release_task_lock
from sdd.workspace import baseline_diff
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
    (root / ".gitignore").write_text("__pycache__/\n*.pyc\n.pytest_cache/\n")
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
    context.spec = Spec(["add health route"], ["GET /health returns ok"])
    context.plan = Plan([Task("health", "add route", ["app/main.py"])])
    context.verify_result = VerifyResult(True)
    context.current_node = "development"
    scheduler.runner_for(done).persist(context)

    def develop(current, tools):
        tools.write_file(
            "app/main.py",
            "from fastapi import FastAPI\napp = FastAPI()\n"
            "@app.get('/health')\ndef health(): return {'status': 'ok'}\n",
            current.iteration,
        )

    context = scheduler.runner_for(done).continue_run(context, done.worktree_path, develop=develop)
    scheduler.sync_from_context("done", context)

    assert Path(done.worktree_path).exists()
    assert git(Path(done.worktree_path), "status", "--porcelain")
    assert "@app.get('/health')" in (
        scheduler.runs_root / done.run_id / "code-diff.patch"
    ).read_text()
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


def test_three_real_m3_tasks_execute_test_archive_and_remain_isolated(tmp_path: Path) -> None:
    repository = fastapi_repo(tmp_path)
    original = (repository / "app" / "main.py").read_text()
    scheduler = LocalScheduler(tmp_path / "state" / "runs", tmp_path / "worktrees", 2)
    for task_id in ("customer-search", "health", "date-format"):
        scheduler.submit_task(repository, task_id, run_id=f"run-{task_id}")
    scheduler.start_ready_tasks()

    # A reaches a genuine Verify ambiguity boundary and releases its slot.
    a = scheduler.get_task("customer-search")
    context_a = scheduler.prepare_run_context(a.task_id, "customer search")
    context_a.spec = Spec(["search customers"], ["matching semantics undefined"])
    context_a.plan = Plan([Task("search", "implement search", ["app/main.py", "tests/test_app.py"])])
    context_a.verify_result = VerifyResult(False, ["matching semantics need owner decision"])
    runner_a = scheduler.runner_for(a)
    runner_a.record_spec(context_a)
    runner_a.record_plan(context_a)
    runner_a.record_verify(context_a)
    context_a.status = "awaiting_human"
    context_a.current_node = "change_spec"
    runner_a.persist(context_a)
    scheduler.sync_from_context(a.task_id, context_a)

    # C obtains A's slot and completes with real source/test changes.
    scheduler.start_ready_tasks()
    c = scheduler.get_task("date-format")
    context_c = scheduler.prepare_run_context(c.task_id, "date format")
    context_c.spec = Spec(["format ISO dates"], ["YYYY/MM/DD output"])
    context_c.plan = Plan([Task("date", "format date", ["app/main.py", "tests/test_app.py"])])
    context_c.verify_result = VerifyResult(True)
    context_c.current_node = "development"
    scheduler.runner_for(c).persist(context_c)

    def develop_c(current, tools):
        tools.write_file("app/main.py", original + "\ndef format_date(value):\n return value.strftime('%Y/%m/%d')\n")
        tools.write_file(
            "tests/test_app.py",
            "from datetime import date\nfrom app.main import format_date\n"
            "def test_date(): assert format_date(date(2026, 7, 22)) == '2026/07/22'\n",
        )

    context_c = scheduler.runner_for(c).continue_run(context_c, c.worktree_path, develop=develop_c)
    scheduler.sync_from_context(c.task_id, context_c)

    # B executes an incorrect health implementation and archives its failed test evidence.
    b = scheduler.get_task("health")
    context_b = scheduler.prepare_run_context(b.task_id, "health endpoint")
    context_b.spec = Spec(["health response"], ["status is ok"])
    context_b.plan = Plan([Task("health", "add health", ["app/main.py", "tests/test_app.py"])])
    context_b.verify_result = VerifyResult(True)
    context_b.current_node = "development"
    context_b.max_iterations = 1
    scheduler.runner_for(b).persist(context_b)

    def develop_b(current, tools):
        tools.write_file("app/main.py", original + "\ndef health(): return {'status': 'bad'}\n")
        tools.write_file(
            "tests/test_app.py",
            "from app.main import health\ndef test_health(): assert health()['status'] == 'ok'\n",
        )

    context_b = scheduler.runner_for(b).continue_run(context_b, b.worktree_path, develop=develop_b)
    assert context_b.status == "failed" and context_b.test_result and not context_b.test_result.passed
    archive_run(context_b, scheduler.runs_root, baseline_diff(context_b.workspace))
    scheduler.sync_from_context(b.task_id, context_b)
    assert scheduler.get_task(c.task_id).status == "completed"

    # A receives the decision, resumes through M3, and performs its own passing change.
    runner_a.apply_spec_change(
        context_a, "define fuzzy matching", ["case-insensitive contains"], "product-owner"
    )
    scheduler.resume_task(a.task_id)
    scheduler.start_ready_tasks()
    resumed_a = runner_a.resume(a.run_id, a.worktree_path)

    def plan_a(current):
        current.plan = Plan([Task("search", "implement search", ["app/main.py", "tests/test_app.py"])])

    def verify_a(current):
        current.verify_result = VerifyResult(True)

    def develop_a(current, tools):
        tools.write_file(
            "app/main.py",
            original + "\nCUSTOMERS = ['Alice', 'Bob']\n"
            "def search_customers(query): return [x for x in CUSTOMERS if query.casefold() in x.casefold()]\n",
        )
        tools.write_file(
            "tests/test_app.py",
            "from app.main import search_customers\n"
            "def test_search(): assert search_customers('ALI') == ['Alice']\n",
        )

    context_a = runner_a.continue_run(
        resumed_a, a.worktree_path, brainstorm=lambda current: None,
        plan=plan_a, verify=verify_a, develop=develop_a,
    )
    scheduler.sync_from_context(a.task_id, context_a)

    contents = {
        task_id: (Path(scheduler.get_task(task_id).worktree_path) / "app" / "main.py").read_text()
        for task_id in ("customer-search", "health", "date-format")
    }
    assert "search_customers" in contents["customer-search"]
    assert "def health" in contents["health"] and "search_customers" not in contents["health"]
    assert "format_date" in contents["date-format"] and "def health" not in contents["date-format"]
    assert (repository / "app" / "main.py").read_text() == original
    assert git(repository, "status", "--porcelain") == ""
    patches = [
        (scheduler.runs_root / f"run-{task_id}" / "code-diff.patch").read_text()
        for task_id in ("customer-search", "health", "date-format")
    ]
    assert len(set(patches)) == 3
    assert all((scheduler.runs_root / f"run-{task_id}" / "archive.md").is_file()
               for task_id in ("customer-search", "health", "date-format"))
