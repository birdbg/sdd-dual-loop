"""Immutable, sequential M3 artifact revisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml

from sdd._persistence import atomic_yaml, plain, validate_run_id
from sdd.models import RunContext, SpecChange


def _revision(context: RunContext, runs_root: str | Path, kind: str, version: int, value: Any) -> Path:
    validate_run_id(context.run_id)
    if value is None:
        raise ValueError(f"cannot save empty {kind}")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ValueError(f"invalid {kind} revision")
    directory = Path(runs_root) / context.run_id
    path = directory / f"{kind}-r{version}.yaml"
    previous = directory / f"{kind}-r{version - 1}.yaml"
    if version > 1 and not previous.exists():
        raise ValueError(f"cannot skip {kind} revision r{version - 1}")
    newer = list(directory.glob(f"{kind}-r*.yaml")) if directory.exists() else []
    if any(_number(item, kind) > version for item in newer):
        raise ValueError(f"cannot save older {kind} revision r{version}")
    if path.exists():
        existing = yaml.safe_load(path.read_text(encoding="utf-8"))
        if existing == plain(value):
            return path
        raise ValueError(f"{kind} revision r{version} already exists with different content")
    return atomic_yaml(path, value)


def _number(path: Path, kind: str) -> int:
    try:
        return int(path.stem.removeprefix(f"{kind}-r"))
    except ValueError:
        return -1


def save_spec_revision(context: RunContext, runs_root: str | Path) -> Path:
    return _revision(context, runs_root, "spec", context.spec_version, context.spec)


def save_plan_revision(context: RunContext, runs_root: str | Path) -> Path:
    if context.plan is None or context.plan.spec_revision != context.spec_version or context.plan.revision != context.plan_version:
        raise ValueError("Plan must reference the current Spec and Plan revisions")
    return _revision(context, runs_root, "plan", context.plan_version, context.plan)


def save_verify_revision(context: RunContext, runs_root: str | Path) -> Path:
    result = context.verify_result
    if result is None or (result.spec_revision, result.plan_revision, result.revision) != (
        context.spec_version, context.plan_version, context.verify_version
    ):
        raise ValueError("Verify must reference the current Spec, Plan, and Verify revisions")
    return _revision(context, runs_root, "verify", context.verify_version, result)


def save_spec_change(change: SpecChange, run_id: str, runs_root: str | Path) -> Path:
    validate_run_id(run_id)
    if not change.change_id.startswith("SC-") or not change.change_id[3:].isdigit():
        raise ValueError("SpecChange id must use SC-NNN format")
    path = Path(runs_root) / run_id / f"spec-change-{change.change_id}.yaml"
    if path.exists():
        if yaml.safe_load(path.read_text(encoding="utf-8")) == plain(change):
            return path
        raise ValueError(f"{change.change_id} already exists with different content")
    return atomic_yaml(path, change)
