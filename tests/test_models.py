from sdd.models import (
    Checkpoint,
    CodeChange,
    Purpose,
    RoutingDecision,
    RunContext,
    SpecChange,
)


def test_run_context_uses_shared_artifact_types() -> None:
    context = RunContext(run_id="run-1", input="add a user query endpoint")
    context.purpose = Purpose(statement="Expose user lookup")
    context.code_changes.append(
        CodeChange(path="app.py", summary="Add query endpoint")
    )

    assert context.current_node == "purpose"
    assert context.max_iterations == 2
    assert context.purpose.statement == "Expose user lookup"
    assert context.code_changes[0].path == "app.py"


def test_run_context_m3_defaults() -> None:
    context = RunContext(run_id="run-2", input="resume a run")

    assert context.spec_version == 1
    assert context.plan_version == 1
    assert context.verify_version == 1
    assert context.last_completed_node is None
    assert context.resume_allowed is False
    assert context.spec_changes == []
    assert context.routing_history == []


def test_run_context_m3_lists_are_not_shared() -> None:
    first = RunContext(run_id="run-3", input="first")
    second = RunContext(run_id="run-4", input="second")
    first.spec_changes.append(
        SpecChange(
            change_id="change-1",
            reason="Clarify behavior",
            changes=["Require an exact match"],
            previous_spec_version=1,
            new_spec_version=2,
            approved_by="reviewer",
            status="approved",
        )
    )
    first.routing_history.append(
        RoutingDecision(
            category="spec_ambiguous",
            source_node="testing",
            target_node="change_spec",
            evidence="Expected behavior is not defined",
            decision="Request manual approval",
        )
    )

    assert second.spec_changes == []
    assert second.routing_history == []


def test_m3_models_can_be_instantiated() -> None:
    checkpoint = Checkpoint(
        run_id="run-5",
        status="paused",
        current_node="testing",
        last_completed_node="development",
        iteration=1,
        spec_version=2,
        plan_version=2,
        verify_version=2,
        base_commit="abc123",
        work_branch="agent/run-5",
        resume_allowed=True,
    )
    spec_change = SpecChange(
        change_id="change-2",
        reason="Resolve ambiguity",
        changes=["Define missing behavior"],
        previous_spec_version=1,
        new_spec_version=2,
        approved_by="product-owner",
        status="approved",
    )
    routing = RoutingDecision(
        category="plan_omission",
        source_node="development",
        target_node="planning",
        evidence="A required file was omitted",
        decision="Regenerate and verify the plan",
    )

    assert checkpoint.last_completed_node == "development"
    assert checkpoint.resume_allowed is True
    assert spec_change.changes == ["Define missing behavior"]
    assert spec_change.new_spec_version == 2
    assert routing.target_node == "planning"
