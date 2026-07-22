"""Safe Git Worktree allocation for one local task."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import subprocess
import uuid

from sdd._persistence import validate_run_id
from sdd.models import TaskRecord


class WorktreeError(RuntimeError):
    pass


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise WorktreeError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.rstrip("\n")


def _repository_root(repository: str | Path) -> Path:
    root = Path(repository).expanduser()
    if not root.is_dir():
        raise WorktreeError("repository does not exist or is not a directory")
    root = root.resolve()
    try:
        top = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
        common = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    except WorktreeError as error:
        raise WorktreeError("repository is not a Git repository") from error
    if top != root:
        raise WorktreeError("repository must be the Git top-level directory")
    if common != (root / ".git").resolve():
        raise WorktreeError("repository must be the primary worktree")
    return root


def _validate_task_id(task_id: str) -> None:
    validate_run_id(task_id)
    if task_id.startswith("-") or any(char.isspace() for char in task_id):
        raise ValueError("task_id must be safe for a Git branch and directory")
    probe = subprocess.run(
        ["git", "check-ref-format", "--branch", f"sdd/{task_id}"],
        text=True, capture_output=True, check=False,
    )
    if probe.returncode:
        raise ValueError("task_id does not form a valid Git branch")


def create_task_worktree(
    repository: str | Path,
    task_id: str,
    worktrees_root: str | Path,
    base_ref: str = "main",
) -> TaskRecord:
    """Create ``sdd/<task-id>`` without changing the primary worktree."""
    _validate_task_id(task_id)
    root = _repository_root(repository)
    worktrees_root = Path(worktrees_root).expanduser().resolve()
    _validate_worktrees_root(root, worktrees_root)
    destination = worktrees_root / task_id
    branch = f"sdd/{task_id}"
    if destination.exists():
        raise WorktreeError(f"worktree path already exists: {destination}")
    if subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=root
    ).returncode == 0:
        raise WorktreeError(f"task branch already exists: {branch}")
    try:
        base_commit = _git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    except WorktreeError as error:
        raise WorktreeError(f"invalid base_ref {base_ref!r}: {error}") from error
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        _git(root, "worktree", "add", "-b", branch, str(destination), base_commit)
        task = TaskRecord(
            task_id=task_id,
            run_id=f"{task_id}-{uuid.uuid4().hex[:12]}",
            repository=str(root),
            worktree_path=str(destination),
            branch=branch,
            base_commit=base_commit,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        validate_task_worktree(task)
        return task
    except BaseException:
        # A normal remove is intentionally used; never force away modifications.
        if destination.exists():
            subprocess.run(
                ["git", "worktree", "remove", str(destination)], cwd=root,
                text=True, capture_output=True, check=False,
            )
            if destination.is_dir():
                try:
                    destination.rmdir()
                except OSError:
                    pass
        subprocess.run(
            ["git", "branch", "-d", branch], cwd=root,
            text=True, capture_output=True, check=False,
        )
        raise


def _validate_worktrees_root(repository: Path, worktrees_root: Path) -> None:
    """Keep task Worktrees outside every Worktree known to this repository."""
    output = _git(repository, "worktree", "list", "--porcelain")
    existing = [
        Path(line.removeprefix("worktree ")).resolve()
        for line in output.splitlines() if line.startswith("worktree ")
    ]
    for worktree in existing:
        if worktrees_root == worktree or worktrees_root.is_relative_to(worktree):
            raise WorktreeError(
                f"worktrees_root must be outside existing Git worktrees: {worktree}"
            )


def validate_task_worktree(task: TaskRecord) -> None:
    _validate_task_id(task.task_id)
    source = _repository_root(task.repository)
    worktree = Path(task.worktree_path).expanduser()
    if not worktree.is_dir():
        raise WorktreeError("task worktree does not exist")
    worktree = worktree.resolve()
    try:
        top = Path(_git(worktree, "rev-parse", "--show-toplevel")).resolve()
        common = Path(_git(worktree, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    except WorktreeError as error:
        raise WorktreeError("task worktree is not a Git worktree") from error
    source_common = Path(_git(source, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    if top != worktree:
        raise WorktreeError("task worktree must be its Git top-level directory")
    if common != source_common:
        raise WorktreeError("task worktree does not belong to the recorded repository")
    if task.branch != f"sdd/{task.task_id}":
        raise WorktreeError("task branch does not match task_id")
    if _git(worktree, "branch", "--show-current") != task.branch:
        raise WorktreeError("worktree branch does not match TaskRecord")
    actual_base = _git(source, "rev-parse", "--verify", f"{task.base_commit}^{{commit}}")
    if actual_base != task.base_commit:
        raise WorktreeError("TaskRecord base_commit is invalid")


def remove_task_worktree(task: TaskRecord) -> None:
    """Remove a clean task Worktree, retaining its branch."""
    validate_task_worktree(task)
    worktree = Path(task.worktree_path).resolve()
    if _git(worktree, "status", "--porcelain=v1", "--untracked-files=all"):
        raise WorktreeError("task worktree has uncommitted changes")
    source = _repository_root(task.repository)
    _git(source, "worktree", "remove", str(worktree))
