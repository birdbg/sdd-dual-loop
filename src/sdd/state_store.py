"""Complete local YAML storage for a resumable RunContext."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

from sdd._persistence import atomic_yaml, load_mapping, validate_run_id
from sdd.models import (
    Archive, BrainstormResult, CodeChange, ExecutionFeedback, Plan, Purpose,
    RefactorResult, RepositoryProfile, RoutingDecision, RunContext, Spec,
    SpecChange, Task, TestExecution, TestResult, ToolOperation, VerifyResult,
    WorkspaceRecord,
)

_STATUSES = {"pending", "running", "awaiting_human", "completed", "failed", "blocked", "rejected"}
_NODES = {"purpose", "brainstorming", "planning", "verify", "development", "testing", "refactor", "archive", "change_spec"}
_FEEDBACK_CATEGORIES = {"code_error", "test_error", "plan_omission", "spec_ambiguous", "purpose_conflict", "blocked"}
_FEEDBACK_TARGETS = {"development", "testing", "planning", "change_spec", "purpose", "archive"}
_REQUIRED = {
    "run_id", "input", "current_node", "status", "purpose", "brainstorm_result",
    "spec", "plan", "verify_result", "code_changes", "test_result",
    "refactor_result", "archive", "iteration", "max_iterations",
    "repository_profile", "workspace", "tool_operations", "test_executions",
    "feedback", "errors", "history", "spec_version", "plan_version",
    "verify_version", "last_completed_node", "resume_allowed",
    "max_spec_revisions", "spec_changes", "routing_history",
}
T = TypeVar("T")


def save_run_context(context: RunContext, runs_root: str | Path) -> Path:
    validate_run_id(context.run_id)
    return atomic_yaml(Path(runs_root) / context.run_id / "run-context.yaml", context)


def _object(cls: type[T], value: Any, name: str) -> T | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"field {name} must be an object or null")
    try:
        return cls(**value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid {name}: {error}") from error


def _list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"field {name} must be a list")
    return value


def load_run_context(run_id: str, runs_root: str | Path) -> RunContext:
    validate_run_id(run_id)
    data = load_mapping(Path(runs_root) / run_id / "run-context.yaml")
    missing = sorted(_REQUIRED - data.keys())
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))
    if data["run_id"] != run_id:
        raise ValueError("run context run_id does not match requested run_id")
    if data["status"] not in _STATUSES:
        raise ValueError(f"unknown status: {data['status']}")
    if data["current_node"] not in _NODES:
        raise ValueError(f"unknown current_node: {data['current_node']}")
    for field in ("iteration", "max_iterations", "spec_version", "plan_version", "verify_version", "max_spec_revisions"):
        if not isinstance(data[field], int) or isinstance(data[field], bool):
            raise ValueError(f"field {field} must be int")
    if not isinstance(data["resume_allowed"], bool):
        raise ValueError("field resume_allowed must be bool")
    if not isinstance(data["input"], str):
        raise ValueError("field input must be str")

    plan_data = data["plan"]
    plan = None
    if plan_data is not None:
        if not isinstance(plan_data, dict) or not isinstance(plan_data.get("tasks"), list):
            raise ValueError("invalid plan")
        try:
            plan = Plan(
                tasks=[Task(**item) for item in plan_data["tasks"]],
                spec_revision=plan_data.get("spec_revision", 1),
                revision=plan_data.get("revision", 1),
            )
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid plan: {error}") from error

    feedback_items = _list(data["feedback"], "feedback")
    if any(
        not isinstance(item, dict)
        or item.get("category") not in _FEEDBACK_CATEGORIES
        or item.get("target") not in _FEEDBACK_TARGETS
        for item in feedback_items
    ):
        raise ValueError("feedback contains an unknown category or target")
    routing_items = _list(data["routing_history"], "routing_history")
    if any(
        not isinstance(item, dict)
        or item.get("category") not in _FEEDBACK_CATEGORIES
        or item.get("target_node") not in _FEEDBACK_TARGETS
        for item in routing_items
    ):
        raise ValueError("routing_history contains an unknown category or target")

    kwargs = dict(
        run_id=data["run_id"], input=data["input"], current_node=data["current_node"], status=data["status"],
        purpose=_object(Purpose, data["purpose"], "purpose"),
        brainstorm_result=_object(BrainstormResult, data["brainstorm_result"], "brainstorm_result"),
        spec=_object(Spec, data["spec"], "spec"), plan=plan,
        verify_result=_object(VerifyResult, data["verify_result"], "verify_result"),
        code_changes=[CodeChange(**item) for item in _list(data["code_changes"], "code_changes")],
        test_result=_object(TestResult, data["test_result"], "test_result"),
        refactor_result=_object(RefactorResult, data["refactor_result"], "refactor_result"),
        archive=_object(Archive, data["archive"], "archive"),
        iteration=data["iteration"], max_iterations=data["max_iterations"],
        repository_profile=_object(RepositoryProfile, data["repository_profile"], "repository_profile"),
        workspace=_object(WorkspaceRecord, data["workspace"], "workspace"),
        tool_operations=[ToolOperation(**item) for item in _list(data["tool_operations"], "tool_operations")],
        test_executions=[TestExecution(**item) for item in _list(data["test_executions"], "test_executions")],
        feedback=[ExecutionFeedback(**item) for item in feedback_items],
        errors=list(_list(data["errors"], "errors")), history=list(_list(data["history"], "history")),
        spec_version=data["spec_version"], plan_version=data["plan_version"], verify_version=data["verify_version"],
        last_completed_node=data["last_completed_node"], resume_allowed=data["resume_allowed"],
        max_spec_revisions=data["max_spec_revisions"],
        spec_changes=[SpecChange(**item) for item in _list(data["spec_changes"], "spec_changes")],
        routing_history=[RoutingDecision(**item) for item in routing_items],
    )
    try:
        return RunContext(**kwargs)
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid run context: {error}") from error
