"""Small sequential M2 coordinator; the eight dual-loop nodes remain unchanged."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sdd.execution_loop.feedback import classify_failure
from sdd.execution_loop.testing import TestRunner
from sdd.intention_loop.archive import archive_run
from sdd.models import RefactorResult, RunContext
from sdd.repository import scan_repository
from sdd.tools import RepositoryTools
from sdd.workspace import WorkspaceError, baseline_diff, create_workspace
from sdd.routing import route_feedback

Develop = Callable[[RunContext, RepositoryTools], None]
Refactor = Callable[[RunContext, RepositoryTools], None]
Replan = Callable[[RunContext], None]


class M2Runner:
    """Prepare, execute, retry, and archive one approved M2 plan.

    Intent artifacts are deliberately supplied through ``RunContext`` so this
    coordinator cannot bypass Purpose, Brainstorming, Plan, or Verify.
    """

    def __init__(self, runs_root: str | Path) -> None:
        self.runs_root = Path(runs_root)

    def run(
        self,
        context: RunContext,
        repository: str | Path,
        develop: Develop,
        *,
        related_tests: list[str] | None = None,
        refactor: Refactor | None = None,
        replan: Replan | None = None,
    ) -> RunContext:
        diff = ""
        try:
            self._require_approved_intent(context)
            context.repository_profile = scan_repository(repository, context.input)
            if not context.repository_profile.supported:
                context.status = "rejected"
                context.errors.extend(context.repository_profile.unresolved)
                return context
            context.workspace = create_workspace(repository, context.run_id)
            tools = RepositoryTools(context.workspace, self._verified_plan_paths(context))
            context.status = "running"
            while True:
                develop(context, tools)
                context.tool_operations = list(tools.operations)
                result, executions = TestRunner(repository, context.repository_profile).run(related_tests)
                context.test_result = result
                context.test_executions.extend(executions)
                if result.passed:
                    if refactor is None:
                        context.refactor_result = RefactorResult(
                            changed=False,
                            summary="未发现有价值且不改变行为的重构项",
                        )
                    else:
                        context.refactor_result = None
                        refactor(context, tools)
                        if context.refactor_result is None:
                            raise ValueError("Refactor callback must set context.refactor_result")
                    context.tool_operations = list(tools.operations)
                    result, executions = TestRunner(repository, context.repository_profile).run(related_tests)
                    context.test_result = result
                    context.test_executions.extend(executions)
                    if result.passed:
                        context.status = "completed"
                        break
                output = executions[-1].output if executions else "; ".join(result.details)
                feedback = classify_failure(output, exit_code=executions[-1].exit_code if executions else 1)
                route_feedback(context, feedback, context.current_node, self.runs_root)
                if feedback.category == "blocked":
                    break
                if feedback.category == "spec_ambiguous":
                    break
                if context.iteration >= context.max_iterations:
                    context.status = "failed"
                    break
                context.iteration += 1
                if feedback.category == "plan_omission":
                    if replan is None:
                        context.status = "blocked"
                        context.errors.append("plan omission requires Plan and Verify callback")
                        break
                    replan(context)
                    if context.verify_result is None or not context.verify_result.approved:
                        context.status = "blocked"
                        context.errors.append("revised Plan was not verified")
                        break
                    tools.allowed_paths = set(self._verified_plan_paths(context))
            diff = baseline_diff(context.workspace)
            return context
        except (ValueError, WorkspaceError, OSError) as error:
            context.status = "blocked"
            context.errors.append(str(error))
            return context
        finally:
            # Even rejected and blocked runs retain evidence; archive failures
            # are not disguised as successful development.
            if context.workspace is not None and not diff:
                diff = baseline_diff(context.workspace)
            archive_run(context, self.runs_root, diff)

    @staticmethod
    def _require_approved_intent(context: RunContext) -> None:
        missing = []
        if context.purpose is None:
            missing.append("Purpose")
        if context.brainstorm_result is None:
            missing.append("Brainstorming")
        if context.spec is None:
            missing.append("Spec")
        if context.plan is None:
            missing.append("Plan")
        if context.verify_result is None or not context.verify_result.approved:
            missing.append("Verify approval")
        if missing:
            raise ValueError("cannot enter Dev before: " + ", ".join(missing))

    @staticmethod
    def _verified_plan_paths(context: RunContext) -> list[str]:
        if context.plan is None:
            return []
        return sorted({path for task in context.plan.tasks for path in task.allowed_paths})
