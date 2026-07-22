"""Safe Git branch isolation and baseline diff support."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from sdd.models import WorkspaceRecord


class WorkspaceError(RuntimeError):
    pass


def create_workspace(repository: str | Path, run_id: str) -> WorkspaceRecord:
    root = Path(repository).resolve(strict=True)
    _git(root, "rev-parse", "--show-toplevel")
    if Path(_git(root, "rev-parse", "--show-toplevel")).resolve() != root:
        raise WorkspaceError("repository path must be the Git top level")
    if _git(root, "status", "--porcelain"):
        raise WorkspaceError("working tree is not clean; existing changes were not touched")

    base_branch = _git(root, "branch", "--show-current")
    if not base_branch:
        raise WorkspaceError("detached HEAD is not supported")
    base_commit = _git(root, "rev-parse", "HEAD")
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", run_id).strip("-.")
    if not safe_id:
        raise WorkspaceError("run_id does not contain a valid branch-name character")
    branch = f"sdd/{safe_id}"
    if _git(root, "branch", "--list", branch):
        raise WorkspaceError(f"work branch already exists: {branch}")
    _git(root, "switch", "-c", branch)
    return WorkspaceRecord(
        repository=str(root), base_branch=base_branch, base_commit=base_commit,
        work_branch=branch, initial_worktree_clean=True,
    )


def baseline_diff(workspace: WorkspaceRecord) -> str:
    root = Path(workspace.repository)
    tracked = _git(root, "diff", "--binary", workspace.base_commit, "--")
    untracked = _git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    additions: list[str] = []
    for relative in untracked:
        result = subprocess.run(
            ["git", "diff", "--no-index", "--binary", "--", "/dev/null", relative],
            cwd=root, text=True, capture_output=True, check=False,
        )
        if result.returncode not in {0, 1}:
            raise WorkspaceError(f"could not diff untracked file {relative}: {result.stderr.strip()}")
        additions.append(result.stdout.strip())
    return "\n".join(part for part in [tracked, *additions] if part)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise WorkspaceError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()
