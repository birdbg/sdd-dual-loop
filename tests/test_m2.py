from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sdd.execution_loop.feedback import classify_failure
from sdd.models import WorkspaceRecord
from sdd.models import BrainstormResult, Plan, Purpose, RunContext, Spec, VerifyResult
from sdd.m2 import M2Runner
from sdd.repository import scan_repository
from sdd.tools import RepositoryTools, ToolBoundaryError
from sdd.workspace import baseline_diff, create_workspace


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(tmp_path: Path, src_layout: bool = True) -> Path:
    root = tmp_path / ("src-layout" if src_layout else "flat-layout")
    package = root / "src" / "shop" if src_layout else root / "service"
    tests = root / "tests"
    package.mkdir(parents=True)
    tests.mkdir()
    (package / "main.py").write_text(
        "from fastapi import FastAPI\nfrom .routes import router\napp = FastAPI()\napp.include_router(router)\n"
    )
    (package / "routes.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.get('/items')\ndef items(): return []\n"
    )
    (tests / "test_items.py").write_text("def test_items(): assert True\n")
    if src_layout:
        (root / "pyproject.toml").write_text(
            "[project]\nname='shop'\nversion='1'\ndependencies=['fastapi']\n[project.optional-dependencies]\ntest=['pytest']\n"
        )
    else:
        (root / "requirements.txt").write_text("fastapi\npytest\n")
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    return root


@pytest.mark.parametrize("src_layout", [True, False])
def test_repository_profile_discovers_two_layouts(tmp_path: Path, src_layout: bool) -> None:
    root = _repo(tmp_path, src_layout)
    profile = scan_repository(root, "Add items filtering")
    assert profile.supported
    assert profile.entrypoints[0].endswith("main.py")
    assert profile.route_files[0].endswith("routes.py")
    assert profile.test_command == "python -m pytest -q"
    assert profile.dependency_file == ("pyproject.toml" if src_layout else "requirements.txt")


def test_workspace_and_tools_are_isolated_and_audited(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    workspace = create_workspace(root, "run:1")
    tools = RepositoryTools(workspace, ["src/shop/routes.py", "src/shop/new.py"])
    tools.write_file("src/shop/routes.py", "# changed\n", iteration=1)
    tools.create_file("src/shop/new.py", "# new file\n", iteration=1)
    assert workspace.base_branch == "main"
    assert workspace.work_branch == "sdd/run-1"
    assert "changed" in baseline_diff(workspace)
    assert "new file" in baseline_diff(workspace)
    assert tools.operations[0].iteration == 1
    with pytest.raises(ToolBoundaryError):
        tools.read_file("../outside")
    with pytest.raises(ToolBoundaryError, match="verified plan"):
        tools.write_file("src/shop/main.py", "# no\n")


def test_workspace_refuses_dirty_tree(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "README.md").write_text("local change")
    with pytest.raises(RuntimeError, match="not clean"):
        create_workspace(root, "run-2")


def test_feedback_routes_plan_and_spec_failures() -> None:
    assert classify_failure("outside verified plan").target == "planning"
    assert classify_failure("ambiguous requirement").target == "change_spec"
    assert classify_failure("AssertionError").target == "development"


def test_runner_reworks_twice_and_archives_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _repo(tmp_path / "target")
    context = RunContext("retry-run", "change items")
    context.purpose = Purpose("change items")
    context.brainstorm_result = BrainstormResult("choice")
    context.spec = Spec(["change items"], ["tests pass"])
    context.plan = Plan()
    context.verify_result = VerifyResult(True)
    calls = 0

    class FailedRunner:
        def __init__(self, *args: object) -> None: pass
        def run(self, *args: object):
            from sdd.models import TestExecution, TestResult
            execution = TestExecution(["python", "-m", "pytest"], str(root), "test", 1, "AssertionError")
            return TestResult(False, 1, 1, ["AssertionError"]), [execution]

    monkeypatch.setattr("sdd.m2.TestRunner", FailedRunner)

    def develop(current: RunContext, tools: RepositoryTools) -> None:
        nonlocal calls
        calls += 1
        tools.write_file("src/shop/routes.py", f"# attempt {calls}\n", current.iteration)

    M2Runner(tmp_path / "runs").run(context, root, ["src/shop/routes.py"], develop)
    assert context.status == "failed"
    assert context.iteration == 2
    assert calls == 3
    assert len(context.feedback) == 3
    assert (tmp_path / "runs" / "retry-run" / "feedback.yaml").exists()
    assert "attempt 3" in (tmp_path / "runs" / "retry-run" / "code-diff.patch").read_text()


def test_runner_uses_real_failure_then_completes(tmp_path: Path) -> None:
    root = _repo(tmp_path / "target")
    (root / "tests" / "test_items.py").write_text(
        "from pathlib import Path\n"
        "def test_implementation():\n"
        "    assert 'fixed' in Path('src/shop/routes.py').read_text()\n"
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "failing acceptance test")
    context = RunContext("success-run", "fix items")
    context.purpose = Purpose("fix items")
    context.brainstorm_result = BrainstormResult("choice")
    context.spec = Spec(["fix items"], ["tests pass"])
    context.plan = Plan()
    context.verify_result = VerifyResult(True)

    def develop(current: RunContext, tools: RepositoryTools) -> None:
        content = "# still broken\n" if current.iteration == 0 else "# fixed\n"
        tools.write_file("src/shop/routes.py", content, current.iteration)

    M2Runner(tmp_path / "runs").run(context, root, ["src/shop/routes.py"], develop)
    assert context.status == "completed"
    assert context.iteration == 1
    assert [run.exit_code for run in context.test_executions] == [1, 0]
    assert (tmp_path / "runs" / "success-run" / "archive.md").exists()
