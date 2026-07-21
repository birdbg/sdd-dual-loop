from sdd.models import CodeChange, Purpose, RunContext


def test_run_context_uses_shared_artifact_types() -> None:
    context = RunContext(run_id="run-1", input="add a user query endpoint")
    context.purpose = Purpose(statement="Expose user lookup")
    context.code_changes.append(
        CodeChange(path="app.py", summary="Add query endpoint")
    )

    assert context.current_node == "purpose"
    assert context.max_iterations == 1
    assert context.purpose.statement == "Expose user lookup"
    assert context.code_changes[0].path == "app.py"
