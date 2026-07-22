from pathlib import Path
import pytest

from sdd.checkpoint import load_checkpoint
from sdd.models import ExecutionFeedback, RunContext
from sdd.routing import route_feedback
from sdd.state_store import load_run_context


@pytest.mark.parametrize("category,target,status", [
    ("code_error", "development", "running"), ("test_error", "testing", "running"),
    ("plan_omission", "planning", "running"), ("spec_ambiguous", "change_spec", "awaiting_human"),
    ("purpose_conflict", "purpose", "running"), ("blocked", "archive", "blocked"),
])
def test_feedback_routes_and_persists(tmp_path: Path, category: str, target: str, status: str) -> None:
    context = RunContext(f"route-{category}", "x", status="running")
    feedback = ExecutionFeedback(category, target, "evidence", "decision")  # type: ignore[arg-type]
    decision = route_feedback(context, feedback, "verify", tmp_path)
    assert (decision.target_node, context.current_node, context.status) == (target, target, status)
    assert context.routing_history == [decision]
    assert load_checkpoint(context.run_id, tmp_path).current_node == target
    assert load_run_context(context.run_id, tmp_path).routing_history == [decision]


def test_unknown_feedback_is_never_guessed(tmp_path: Path) -> None:
    context = RunContext("unknown", "x")
    with pytest.raises(ValueError, match="unknown"):
        route_feedback(context, ExecutionFeedback("other", "archive", "x", "x"), "test", tmp_path)  # type: ignore[arg-type]
