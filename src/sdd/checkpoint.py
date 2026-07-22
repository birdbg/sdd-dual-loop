"""Atomic, strict checkpoint persistence."""

from pathlib import Path

from sdd._persistence import atomic_yaml, load_mapping, require_exact_fields, validate_run_id
from sdd.models import Checkpoint, RunContext

_FIELDS = {
    "run_id": str, "status": str, "current_node": str,
    "last_completed_node": (str, type(None)), "iteration": int,
    "spec_version": int, "plan_version": int, "verify_version": int,
    "base_commit": str, "work_branch": str, "resume_allowed": bool,
}


def save_checkpoint(context: RunContext, runs_root: str | Path) -> Checkpoint:
    validate_run_id(context.run_id)
    workspace = context.workspace
    checkpoint = Checkpoint(
        run_id=context.run_id, status=context.status, current_node=context.current_node,
        last_completed_node=context.last_completed_node, iteration=context.iteration,
        spec_version=context.spec_version, plan_version=context.plan_version,
        verify_version=context.verify_version,
        base_commit=workspace.base_commit if workspace else "",
        work_branch=workspace.work_branch if workspace else "",
        resume_allowed=context.resume_allowed,
    )
    atomic_yaml(Path(runs_root) / context.run_id / "checkpoint.yaml", checkpoint)
    return checkpoint


def load_checkpoint(run_id: str, runs_root: str | Path) -> Checkpoint:
    validate_run_id(run_id)
    data = load_mapping(Path(runs_root) / run_id / "checkpoint.yaml")
    require_exact_fields(data, _FIELDS)
    try:
        checkpoint = Checkpoint(**data)
    except TypeError as error:
        raise ValueError(f"invalid checkpoint fields: {error}") from error
    if checkpoint.run_id != run_id:
        raise ValueError("checkpoint run_id does not match requested run_id")
    return checkpoint
