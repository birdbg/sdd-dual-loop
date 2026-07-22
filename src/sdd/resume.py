"""Read-only validation for safely resuming one local M3 run."""

from __future__ import annotations

import subprocess
from pathlib import Path

from sdd.checkpoint import load_checkpoint
from sdd.state_store import load_run_context


class ResumeError(RuntimeError):
    pass


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
    if result.returncode:
        raise ResumeError(f"git {' '.join(args)} failed: {(result.stderr or result.stdout).strip()}")
    return result.stdout.rstrip("\n")


def resume_run(run_id: str, runs_root: str | Path, repository: str | Path):
    try:
        checkpoint = load_checkpoint(run_id, runs_root)
        context = load_run_context(run_id, runs_root)
    except (FileNotFoundError, ValueError, OSError) as error:
        raise ResumeError(f"invalid persisted run: {error}") from error
    if checkpoint.run_id != context.run_id:
        raise ResumeError("checkpoint and RunContext run_id differ")
    if checkpoint.status != context.status:
        raise ResumeError("checkpoint and RunContext status differ")
    for field in ("current_node", "last_completed_node", "iteration", "spec_version", "plan_version", "verify_version", "resume_allowed"):
        if getattr(checkpoint, field) != getattr(context, field):
            raise ResumeError(f"checkpoint and RunContext {field} differ")
    if not checkpoint.resume_allowed:
        raise ResumeError("resume is not allowed by checkpoint")
    if checkpoint.status not in {"running", "awaiting_human", "blocked"}:
        raise ResumeError(f"status {checkpoint.status} cannot be resumed")

    root = Path(repository)
    if not root.exists() or not root.is_dir():
        raise ResumeError("repository does not exist")
    root = root.resolve()
    try:
        top = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
    except ResumeError as error:
        raise ResumeError("repository is not a Git repository") from error
    if top != root:
        raise ResumeError("repository must be the Git top-level directory")
    if context.workspace is None:
        raise ResumeError("RunContext has no workspace record")
    if Path(context.workspace.repository).resolve() != root:
        raise ResumeError("workspace repository does not match repository")
    if checkpoint.work_branch != context.workspace.work_branch or checkpoint.base_commit != context.workspace.base_commit:
        raise ResumeError("checkpoint and workspace Git identity differ")
    if _git(root, "branch", "--show-current") != checkpoint.work_branch:
        raise ResumeError("current branch does not match checkpoint work_branch")
    if not checkpoint.base_commit:
        raise ResumeError("checkpoint base_commit is empty")
    probe = subprocess.run(["git", "cat-file", "-e", f"{checkpoint.base_commit}^{{commit}}"], cwd=root, capture_output=True)
    if probe.returncode:
        raise ResumeError("checkpoint base_commit no longer exists")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", checkpoint.base_commit, "HEAD"], cwd=root, capture_output=True)
    if ancestor.returncode != 0:
        raise ResumeError("current branch history does not contain base_commit")

    allowed = {item.path for item in context.tool_operations} | {item.path for item in context.code_changes}
    unknown: list[str] = []
    for line in _git(root, "status", "--porcelain=v1", "--untracked-files=all").splitlines():
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path not in allowed:
            unknown.append(path)
    if unknown:
        raise ResumeError("working tree contains unexplained changes: " + ", ".join(sorted(unknown)))
    return context
