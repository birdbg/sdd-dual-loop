from pathlib import Path
import pytest

from sdd.change_spec import apply_spec_change
from sdd.models import Plan, RunContext, Spec, VerifyResult


def _context() -> RunContext:
    value = RunContext("change", "x", current_node="change_spec", status="awaiting_human")
    value.spec = Spec(["original"], ["works"])
    return value


def test_two_human_changes_create_r2_and_r3(tmp_path: Path) -> None:
    context = _context()
    from sdd.versioning import save_spec_revision
    save_spec_revision(context, tmp_path)
    apply_spec_change(context, "clarify", ["case insensitive"], "owner", tmp_path)
    assert context.spec_version == 2 and context.current_node == "brainstorming"
    context.current_node, context.status = "change_spec", "awaiting_human"
    apply_spec_change(context, "clarify again", ["contains"], "owner", tmp_path)
    assert [item.change_id for item in context.spec_changes] == ["SC-001", "SC-002"]
    assert context.spec_version == 3
    assert (tmp_path / "change" / "spec-r1.yaml").exists()
    assert (tmp_path / "change" / "spec-r3.yaml").exists()


@pytest.mark.parametrize("field,value", [("status", "running"), ("current_node", "verify")])
def test_change_requires_human_boundary(tmp_path: Path, field: str, value: str) -> None:
    context = _context()
    setattr(context, field, value)
    with pytest.raises(ValueError):
        apply_spec_change(context, "reason", ["change"], "owner", tmp_path)


@pytest.mark.parametrize("reason,changes,approver", [("", ["x"], "a"), ("x", [], "a"), ("x", [""], "a"), ("x", ["y"], "")])
def test_change_validates_human_input(tmp_path: Path, reason: str, changes: list[str], approver: str) -> None:
    with pytest.raises(ValueError):
        apply_spec_change(_context(), reason, changes, approver, tmp_path)


def test_change_limit_pauses_safely(tmp_path: Path) -> None:
    context = _context()
    context.max_spec_revisions = 0
    with pytest.raises(ValueError, match="maximum"):
        apply_spec_change(context, "reason", ["change"], "owner", tmp_path)
    assert context.status == "awaiting_human"


def test_structured_change_removes_ambiguity_and_invalidates_old_intent(tmp_path: Path) -> None:
    context = _context()
    context.plan = Plan(spec_revision=1, revision=1)
    context.verify_result = VerifyResult(False)
    apply_spec_change(
        context, "resolve semantics",
        ["case insensitive", "contains match", "return all matching orders"],
        "owner", tmp_path,
        remove_acceptance_criteria=["works"],
        add_acceptance_criteria=["no match returns HTTP 200", "response is an empty list"],
    )
    assert context.spec == Spec(
        ["original", "case insensitive", "contains match", "return all matching orders"],
        ["no match returns HTTP 200", "response is an empty list"],
    )
    assert context.plan is None
    assert context.verify_result is None
