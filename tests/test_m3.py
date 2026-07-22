from pathlib import Path
import subprocess
import pytest

from sdd.change_spec import apply_spec_change
from sdd.m3 import M3Runner
from sdd.models import (
    BrainstormResult, ExecutionFeedback, Plan, Purpose, RefactorResult, RunContext,
    RepositoryProfile, Spec, Task, TestExecution as SddTestExecution,
    TestResult as SddTestResult, VerifyResult,
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
    runner.apply_spec_change(context, "resolve search semantics", [
        "case insensitive", "contains match", "return all matches", "HTTP 200 with an empty list",
    ], "product-owner", remove_acceptance_criteria=["unspecified matching"])
    context.verify_result = VerifyResult(True)
    with pytest.raises(ValueError, match="Plan"):
        runner.record_verify(context, revised=True)
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


def _workspace(tmp_path: Path, run_id: str):
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "app.py").write_text("value = 1\n", encoding="utf-8")
    (repository / "test_app.py").write_text("def test_value(): pass\n", encoding="utf-8")
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.email", "test@example.com")
    _git(repository, "config", "user.name", "Test")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "base")
    return repository, create_workspace(repository, run_id)


def test_plan_omission_creates_plan_and_verify_r2_without_overwrite(tmp_path: Path) -> None:
    repository, workspace = _workspace(tmp_path, "replan")
    runner = M3Runner(tmp_path / "runs")
    context = RunContext("replan", "x", status="running")
    context.workspace = workspace
    context.spec = Spec(["requirement"], ["criterion"])
    runner.record_spec(context)
    context.plan = Plan([Task("r1", "first plan", ["app.py"])])
    runner.record_plan(context)
    context.verify_result = VerifyResult(False, ["plan omission"])
    runner.record_verify(context)
    first_plan = (runner.runs_root / "replan" / "plan-r1.yaml").read_text(encoding="utf-8")
    runner.route_feedback(
        context,
        ExecutionFeedback("plan_omission", "planning", "missing planned file", "revise plan"),
        "verify",
    )

    def revise_plan(current):
        current.plan = Plan([Task("r2", "revised plan", ["app.py"])])

    def revise_verify(current):
        current.verify_result = VerifyResult(False, ["stop before development"])

    runner.continue_run(context, repository, develop=lambda *_: None,
                        plan=revise_plan, verify=revise_verify)
    assert (context.plan_version, context.verify_version) == (2, 2)
    assert (runner.runs_root / "replan" / "plan-r1.yaml").read_text(encoding="utf-8") == first_plan
    assert (runner.runs_root / "replan" / "plan-r2.yaml").exists()
    assert (runner.runs_root / "replan" / "verify-r2.yaml").exists()


def test_test_error_uses_repair_callback_before_rerun(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository, workspace = _workspace(tmp_path, "repair")
    runner = M3Runner(tmp_path / "runs")
    context = RunContext("repair", "x", current_node="testing", status="running")
    context.workspace = workspace
    context.repository_profile = RepositoryProfile(test_command="python -m pytest")
    context.plan = Plan([Task("test", "repair fixture", ["test_app.py"])])
    calls = 0

    class SequencedRunner:
        def __init__(self, *_args):
            pass

        def run(self, _related=None):
            nonlocal calls
            calls += 1
            passed = calls > 1
            output = "passed" if passed else "fixture broken"
            execution = SddTestExecution(["pytest"], str(repository), "test", 0 if passed else 1, output)
            return SddTestResult(passed, 1, 0 if passed else 1, [output]), [execution]

    monkeypatch.setattr("sdd.m3.TestRunner", SequencedRunner)
    repairs = []

    def repair_test(current, tools):
        repairs.append(current.iteration)
        tools.write_file("test_app.py", "def test_value(): assert True\n", current.iteration)

    runner.continue_run(context, repository, develop=lambda *_: None, repair_test=repair_test)
    assert repairs == [1]
    assert calls == 3  # failed test, repaired test, post-refactor safety test
    assert context.status == "completed"


def test_blocked_run_requires_audited_unblock(tmp_path: Path) -> None:
    repository, workspace = _workspace(tmp_path, "blocked")
    runner = M3Runner(tmp_path / "runs")
    context = RunContext("blocked", "x", current_node="archive", status="blocked")
    context.workspace = workspace
    runner.persist(context)
    with pytest.raises(ValueError, match="explicit unblock"):
        runner.continue_run(context, repository, develop=lambda *_: None)
    assert context.status == "blocked"

    runner.unblock(context, target_node="verify", reason="dependency restored")
    context.plan = Plan()

    def verify(current):
        current.verify_result = VerifyResult(False, ["operator review"])

    runner.continue_run(context, repository, develop=lambda *_: None, verify=verify)
    assert context.status == "running"
    assert context.current_node == "verify"
    assert context.history[-1] == "unblock:archive->verify: dependency restored"


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
    context = runner.resume(context.run_id, repository)
    runner.apply_spec_change(context, "define order search behavior", [
        "customer name matching is case insensitive",
        "customer name uses contains matching",
        "return every matching order",
    ], "product-owner",
        remove_acceptance_criteria=["matching semantics unspecified"],
        add_acceptance_criteria=["no result returns HTTP 200", "response is an empty list"])

    def brainstorm(current):
        current.history.append("brainstorming-r2")

    def plan(current):
        current.plan = Plan([Task("orders-r2", "implement clarified search", ["app/main.py"])])

    # Continue through the intention loop and stop at Verify for the second interruption.
    with pytest.raises(ValueError, match="verify callback"):
        runner.continue_run(context, repository, develop=lambda *_: None,
                            brainstorm=brainstorm, plan=plan)

    # Second process interruption resumes at Verify, without branch creation.
    context = runner.resume(context.run_id, repository)
    assert context.current_node == "verify"
    branch_before = subprocess.run(["git", "branch", "--show-current"], cwd=repository,
                                   text=True, check=True, capture_output=True).stdout.strip()

    def verify(current):
        current.verify_result = VerifyResult(True)

    def develop(current, tools):
        tools.write_file("app/main.py", (
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "ORDERS = [{'id': 1, 'customer_name': 'Alice'}, {'id': 2, 'customer_name': 'ALICIA'}, "
            "{'id': 3, 'customer_name': 'Bob'}]\n"
            "@app.get('/orders')\n"
            "def orders(customer_name: str):\n"
            " needle = customer_name.casefold()\n"
            " return [order for order in ORDERS if needle in order['customer_name'].casefold()]\n"
        ), current.iteration)

    context = runner.resume_and_continue(context.run_id, repository, verify=verify,
                                         develop=develop)
    assert subprocess.run(["git", "branch", "--show-current"], cwd=repository,
                          text=True, check=True, capture_output=True).stdout.strip() == branch_before

    run_dir = runs / context.run_id
    assert context.status == "completed"
    assert [run.exit_code for run in context.test_executions] == [0, 0]
    assert (run_dir / "spec-r1.yaml").read_text() != (run_dir / "spec-r2.yaml").read_text()
    assert context.routing_history[0].target_node == "change_spec"
    assert context.plan.spec_revision == 2
    assert context.verify_result.plan_revision == 2
    assert "matching semantics unspecified" not in context.spec.acceptance_criteria
    assert all((run_dir / name).exists() for name in [
        "checkpoint.yaml", "run-context.yaml", "routing-history.yaml", "archive.md", "code-diff.patch"
    ])
