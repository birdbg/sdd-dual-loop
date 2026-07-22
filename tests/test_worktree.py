from pathlib import Path
import subprocess

import pytest

from sdd.models import TaskRecord
from sdd.worktree import WorktreeError, create_task_worktree, remove_task_worktree, validate_task_worktree


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


def test_two_tasks_are_isolated_without_switching_primary(repository: Path, tmp_path: Path) -> None:
    before = git(repository, "branch", "--show-current")
    a = create_task_worktree(repository, "a", tmp_path / "trees")
    b = create_task_worktree(repository, "b", tmp_path / "trees")
    assert a.worktree_path != b.worktree_path
    assert a.branch != b.branch
    assert git(repository, "branch", "--show-current") == before
    remove_task_worktree(a)
    assert git(repository, "show-ref", "--verify", "refs/heads/sdd/a")


def test_duplicate_identity_is_rejected(repository: Path, tmp_path: Path) -> None:
    task = create_task_worktree(repository, "same", tmp_path / "trees")
    with pytest.raises(WorktreeError, match="path already exists"):
        create_task_worktree(repository, "same", tmp_path / "trees")
    alias = TaskRecord(**{name: getattr(task, name) for name in task.__dataclass_fields__})
    alias.task_id = "different"
    with pytest.raises(WorktreeError, match="branch does not match"):
        validate_task_worktree(alias)


def test_invalid_repository_and_non_top_level_are_rejected(tmp_path: Path, repository: Path) -> None:
    (tmp_path / "missing").mkdir()
    with pytest.raises(WorktreeError, match="not a Git"):
        create_task_worktree(tmp_path / "missing", "a", tmp_path / "trees")
    child = repository / "child"
    child.mkdir()
    with pytest.raises(WorktreeError, match="top-level"):
        create_task_worktree(child, "a", tmp_path / "trees")


def test_branch_mismatch_is_rejected(repository: Path, tmp_path: Path) -> None:
    task = create_task_worktree(repository, "mismatch", tmp_path / "trees")
    git(Path(task.worktree_path), "switch", "--detach")
    with pytest.raises(WorktreeError, match="branch"):
        validate_task_worktree(task)


def test_worktrees_root_inside_source_repository_is_rejected_without_pollution(
    repository: Path,
) -> None:
    before = git(repository, "status", "--porcelain")
    with pytest.raises(WorktreeError, match="outside existing Git worktrees"):
        create_task_worktree(repository, "nested", repository / ".sdd-worktrees")
    assert git(repository, "status", "--porcelain") == before == ""
    assert not (repository / ".sdd-worktrees").exists()
