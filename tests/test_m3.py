from pathlib import Path
import subprocess

from sdd.change_spec import apply_spec_change
from sdd.m3 import M3Runner
from sdd.models import (
    BrainstormResult, ExecutionFeedback, Plan, Purpose, RefactorResult, RunContext,
    Spec, Task, VerifyResult,
)
from sdd.routing import route_feedback
from sdd.resume import resume_run
from sdd.repository import scan_repository
from sdd.workspace import baseline_diff, create_workspace
from sdd.tools import RepositoryTools
from sdd.execution_loop.testing import TestRunner as SddTestRunner
from sdd.intention_loop.archive import archive_run


def test_ambiguity_resume_lifecycle_keeps_revision_links(tmp_path: Path) -> None:
    context = RunContext("orders", "按客户名称搜索", status="running")
    context.spec = Spec(["search by customer name"], ["unspecified matching"])
    runner = M3Runner(tmp_path)
    runner.record_spec(context)
    context.plan = Plan()
    runner.record_plan(context)
    context.verify_result = VerifyResult(False, ["matching behavior ambiguous"])
    runner.record_verify(context)
    route_feedback(
        context,
        ExecutionFeedback("spec_ambiguous", "change_spec", "four choices unspecified", "request human decision"),
        "verify", tmp_path,
    )
    apply_spec_change(context, "resolve search semantics", [
        "case insensitive", "contains match", "return all matches", "HTTP 200 with an empty list",
    ], "product-owner", tmp_path)
    context.plan = Plan()
    runner.record_plan(context, revised=True)
    context.verify_result = VerifyResult(True)
    runner.record_verify(context, revised=True)
    assert context.current_node == "development"
    assert (context.plan.spec_revision, context.plan.revision) == (2, 2)
    assert (context.verify_result.spec_revision, context.verify_result.plan_revision, context.verify_result.revision) == (2, 2, 2)
    assert (tmp_path / "orders" / "spec-r1.yaml").exists()
    assert (tmp_path / "orders" / "spec-r2.yaml").exists()


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_order_search_end_to_end_with_two_interruptions(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    (repository / "app").mkdir(parents=True)
    (repository / "tests").mkdir()
    (repository / "app" / "__init__.py").write_text("", encoding="utf-8")
    (repository / "app" / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )
    (repository / "tests" / "test_orders.py").write_text(
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "client = TestClient(app)\n"
        "def test_contains_case_insensitive_and_all_matches():\n"
        " response = client.get('/orders', params={'customer_name': 'ali'})\n"
        " assert response.status_code == 200\n"
        " assert [x['customer_name'] for x in response.json()] == ['Alice', 'ALICIA']\n"
        "def test_no_match_is_empty_200():\n"
        " response = client.get('/orders', params={'customer_name': 'nobody'})\n"
        " assert response.status_code == 200\n"
        " assert response.json() == []\n",
        encoding="utf-8",
    )
    (repository / "pyproject.toml").write_text(
        "[project]\nname='orders'\nversion='1'\ndependencies=['fastapi']\n"
        "[project.optional-dependencies]\ntest=['pytest']\n",
        encoding="utf-8",
    )
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.email", "test@example.com")
    _git(repository, "config", "user.name", "Test")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "base")

    runs = tmp_path / "runs"
    runner = M3Runner(runs)
    context = RunContext("order-search", "为订单接口增加按客户名称搜索功能", status="running")
    context.purpose = Purpose("支持按客户名称查找订单")
    context.brainstorm_result = BrainstormResult("query parameter")
    context.spec = Spec(["search by customer_name"], ["matching semantics unspecified"])
    context.repository_profile = scan_repository(repository, context.input)
    context.workspace = create_workspace(repository, context.run_id)
    context.history.extend(["purpose", "brainstorming"])
    runner.record_spec(context)
    context.plan = Plan([Task("orders", "implement search", ["app/main.py"])])
    runner.record_plan(context)
    context.verify_result = VerifyResult(False, ["case, match, multiplicity, no-result are ambiguous"])
    runner.record_verify(context)
    route_feedback(context, ExecutionFeedback(
        "spec_ambiguous", "change_spec", "four search rules unspecified", "request product owner approval"
    ), "verify", runs)

    # First process interruption: only persisted YAML is used afterward.
    context = resume_run(context.run_id, runs, repository)
    apply_spec_change(context, "define order search behavior", [
        "customer name matching is case insensitive",
        "customer name uses contains matching",
        "return every matching order",
        "no result returns HTTP 200 and an empty list",
    ], "product-owner", runs)
    context.history.append("brainstorming-r2")
    context.plan = Plan([Task("orders-r2", "implement clarified search", ["app/main.py"])])
    runner.record_plan(context, revised=True)

    # Second process interruption resumes at Verify, without branch creation.
    context = resume_run(context.run_id, runs, repository)
    assert context.current_node == "verify"
    context.verify_result = VerifyResult(True)
    runner.record_verify(context, revised=True)
    tools = RepositoryTools(context.workspace, ["app/main.py"])
    tools.write_file("app/main.py", (
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "ORDERS = [{'id': 1, 'customer_name': 'Alice'}, {'id': 2, 'customer_name': 'ALICIA'}, "
        "{'id': 3, 'customer_name': 'Bob'}]\n"
        "@app.get('/orders')\n"
        "def orders(customer_name: str):\n"
        " needle = customer_name.casefold()\n"
        " return [order for order in ORDERS if needle in order['customer_name'].casefold()]\n"
    ), context.iteration)
    context.tool_operations = list(tools.operations)
    result, executions = SddTestRunner(repository, context.repository_profile).run()
    context.test_result = result
    context.test_executions.extend(executions)
    assert result.passed
    context.refactor_result = RefactorResult(False, "implementation is already minimal")
    result, executions = SddTestRunner(repository, context.repository_profile).run()
    context.test_result = result
    context.test_executions.extend(executions)
    assert result.passed
    context.status, context.current_node = "completed", "archive"
    context.last_completed_node, context.resume_allowed = "refactor", False
    archive_run(context, runs, baseline_diff(context.workspace))

    run_dir = runs / context.run_id
    assert context.status == "completed"
    assert [run.exit_code for run in context.test_executions] == [0, 0]
    assert (run_dir / "spec-r1.yaml").read_text() != (run_dir / "spec-r2.yaml").read_text()
    assert context.routing_history[0].target_node == "change_spec"
    assert context.plan.spec_revision == 2
    assert context.verify_result.plan_revision == 2
    assert all((run_dir / name).exists() for name in [
        "checkpoint.yaml", "run-context.yaml", "routing-history.yaml", "archive.md", "code-diff.patch"
    ])
