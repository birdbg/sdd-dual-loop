from pathlib import Path
import subprocess
import pytest

from sdd.checkpoint import save_checkpoint
from sdd.models import RunContext, ToolOperation, WorkspaceRecord
from sdd.resume import ResumeError, resume_run
from sdd.state_store import save_run_context


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, text=True, check=True, capture_output=True).stdout.strip()


def _persisted(tmp_path: Path, status: str = "running", resume_allowed: bool = True) -> tuple[Path, Path, RunContext]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / "known.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "switch", "-c", "sdd/resume")
    context = RunContext("resume", "x", status=status, resume_allowed=resume_allowed)
    context.workspace = WorkspaceRecord(str(repo), "main", base, "sdd/resume", True)
    runs = tmp_path / "runs"
    save_checkpoint(context, runs)
    save_run_context(context, runs)
    return repo, runs, context


@pytest.mark.parametrize("status", ["running", "awaiting_human", "blocked"])
def test_allowed_statuses_resume_without_git_mutation(tmp_path: Path, status: str) -> None:
    repo, runs, context = _persisted(tmp_path, status)
    assert resume_run("resume", runs, repo) == context
    assert _git(repo, "branch", "--show-current") == "sdd/resume"


@pytest.mark.parametrize("status", ["completed", "failed", "rejected"])
def test_terminal_statuses_cannot_resume(tmp_path: Path, status: str) -> None:
    repo, runs, _ = _persisted(tmp_path, status)
    with pytest.raises(ResumeError, match="cannot be resumed"):
        resume_run("resume", runs, repo)


def test_resume_rejects_unexplained_changes_and_false_permission(tmp_path: Path) -> None:
    repo, runs, _ = _persisted(tmp_path, resume_allowed=False)
    with pytest.raises(ResumeError, match="not allowed"):
        resume_run("resume", runs, repo)
    repo, runs, _ = _persisted(tmp_path / "second")
    (repo / "unknown.txt").write_text("unknown", encoding="utf-8")
    with pytest.raises(ResumeError, match="unexplained"):
        resume_run("resume", runs, repo)


def test_recorded_tool_change_is_explainable(tmp_path: Path) -> None:
    repo, runs, context = _persisted(tmp_path)
    context.tool_operations.append(ToolOperation("known.txt", "write", 0))
    (repo / "known.txt").write_text("changed\n", encoding="utf-8")
    save_checkpoint(context, runs)
    save_run_context(context, runs)
    assert resume_run("resume", runs, repo).tool_operations == context.tool_operations
