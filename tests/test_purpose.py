import pytest

from sdd.intention_loop.purpose import PurposeNode
from sdd.models import RunContext


def test_purpose_node_updates_and_returns_the_same_context() -> None:
    captured_prompt = ""

    def complete(prompt: str) -> str:
        nonlocal captured_prompt
        captured_prompt = prompt
        return """
statement: Allow clients to query one user by ID
success_criteria:
  - Existing users return their id, username, and email
  - Missing users return a not-found response
"""

    context = RunContext(
        run_id="run-1",
        input="Add GET /users/{user_id} to the existing FastAPI app.",
    )

    result = PurposeNode(complete).run(context)

    assert result is context
    assert context.purpose is not None
    assert context.purpose.statement == "Allow clients to query one user by ID"
    assert context.current_node == "brainstorming"
    assert context.status == "running"
    assert context.history == ["purpose:completed"]
    assert "# Purpose 节点" in captured_prompt
    assert context.input in captured_prompt


def test_purpose_node_records_invalid_model_output() -> None:
    context = RunContext(run_id="run-2", input="Add a user query endpoint.")

    with pytest.raises(ValueError, match="success_criteria"):
        PurposeNode(lambda _: "statement: Incomplete output").run(context)

    assert context.purpose is None
    assert context.current_node == "purpose"
    assert context.status == "failed"
    assert context.errors == [
        "purpose: Purpose.success_criteria must be a list of strings"
    ]
