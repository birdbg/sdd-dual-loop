from pathlib import Path
import pytest

from sdd.models import (
    ExecutionFeedback, Plan, RoutingDecision, RunContext, Spec, SpecChange, Task,
    VerifyResult, WorkspaceRecord,
)
from sdd.state_store import load_run_context, save_run_context


def test_complete_context_round_trip_has_independent_lists(tmp_path: Path) -> None:
    context = RunContext("state-1", "search", status="awaiting_human", current_node="change_spec", resume_allowed=True)
    context.spec = Spec(["search"], ["200"])
    context.plan = Plan([Task("t", "implement")], 1, 1)
    context.verify_result = VerifyResult(False, ["ambiguous"])
    context.workspace = WorkspaceRecord("/repo", "main", "abc", "sdd/state-1", True)
    context.spec_changes.append(SpecChange("SC-001", "why", ["clear"], 1, 2, "human", "approved"))
    context.routing_history.append(RoutingDecision("spec_ambiguous", "verify", "change_spec", "x", "ask"))
    context.feedback.append(ExecutionFeedback("spec_ambiguous", "change_spec", "x", "ask"))
    save_run_context(context, tmp_path)
    first = load_run_context("state-1", tmp_path)
    second = load_run_context("state-1", tmp_path)
    assert first == context
    assert isinstance(first.plan.tasks[0], Task)
    assert isinstance(first.spec_changes[0], SpecChange)
    assert isinstance(first.routing_history[0], RoutingDecision)
    first.errors.append("new")
    assert second.errors == []


def test_context_rejects_invalid_yaml_and_unknown_status(tmp_path: Path) -> None:
    context = RunContext("bad-state", "x")
    path = save_run_context(context, tmp_path)
    path.write_text("[invalid", encoding="utf-8")
    with pytest.raises(ValueError):
        load_run_context("bad-state", tmp_path)
    save_run_context(context, tmp_path)
    text = path.read_text(encoding="utf-8").replace("status: pending", "status: mystery")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="unknown status"):
        load_run_context("bad-state", tmp_path)
