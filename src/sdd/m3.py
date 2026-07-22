"""Thin M3 lifecycle layer over the existing sequential M2 runner."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sdd.checkpoint import save_checkpoint
from sdd.change_spec import apply_spec_change
from sdd.execution_loop.feedback import classify_failure
from sdd.execution_loop.testing import TestRunner
from sdd.intention_loop.archive import archive_run
from sdd.m2 import M2Runner
from sdd.models import ExecutionFeedback, RefactorResult, RunContext
from sdd.routing import route_feedback
from sdd.resume import resume_run
from sdd.state_store import save_run_context
from sdd.tools import RepositoryTools
from sdd.workspace import baseline_diff
from sdd.versioning import save_plan_revision, save_spec_revision, save_verify_revision


class M3Runner(M2Runner):
    """Adds durable node boundaries without introducing a workflow engine."""

    def persist(self, context: RunContext, completed_node: str | None = None) -> None:
        if completed_node is not None:
            context.last_completed_node = completed_node
        context.resume_allowed = context.status in {"running", "awaiting_human", "blocked"}
        save_checkpoint(context, self.runs_root)
        save_run_context(context, self.runs_root)

    def record_spec(self, context: RunContext) -> Path:
        path = save_spec_revision(context, self.runs_root)
        self.persist(context, "brainstorming")
        return path

    def record_plan(self, context: RunContext, *, revised: bool = False) -> Path:
        if context.plan is None:
            raise ValueError("Plan is required")
        if revised:
            context.plan_version += 1
        context.plan.spec_revision = context.spec_version
        context.plan.revision = context.plan_version
        path = save_plan_revision(context, self.runs_root)
        context.current_node = "verify"
        self.persist(context, "planning")
        return path

    def record_verify(self, context: RunContext, *, revised: bool = False) -> Path:
        if context.verify_result is None:
            raise ValueError("VerifyResult is required")
        if context.plan is None or context.plan.spec_revision != context.spec_version:
            raise ValueError("Verify requires a Plan based on the current Spec revision")
        if context.plan.revision != context.plan_version:
            raise ValueError("Verify requires the current Plan revision")
        if revised:
            context.verify_version += 1
        result = context.verify_result
        result.spec_revision = context.spec_version
        result.plan_revision = context.plan_version
        result.revision = context.verify_version
        path = save_verify_revision(context, self.runs_root)
        context.current_node = "development" if result.approved else "verify"
        self.persist(context, "verify")
        return path

    def resume(self, run_id: str, repository: str | Path) -> RunContext:
        return resume_run(run_id, self.runs_root, repository)

    def route_feedback(self, context: RunContext, feedback: ExecutionFeedback, source_node: str) -> None:
        route_feedback(context, feedback, source_node, self.runs_root)

    def apply_spec_change(self, context: RunContext, reason: str, changes: list[str],
                          approved_by: str, **revisions: object) -> RunContext:
        return apply_spec_change(
            context, reason, changes, approved_by, self.runs_root, **revisions
        )

    def resume_and_continue(self, run_id: str, repository: str | Path, **callbacks: object) -> RunContext:
        context = self.resume(run_id, repository)
        return self.continue_run(context, repository, **callbacks)

    def unblock(self, context: RunContext, *, target_node: str, reason: str) -> RunContext:
        """Record an explicit operator decision before a blocked run can continue."""
        allowed_targets = {"brainstorming", "planning", "verify", "development", "testing", "refactor"}
        if context.status != "blocked":
            raise ValueError("only a blocked run can be unblocked")
        if target_node not in allowed_targets:
            raise ValueError("invalid unblock target node")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("unblock reason must be non-empty")
        previous = context.current_node
        context.current_node = target_node
        context.status = "running"
        context.history.append(f"unblock:{previous}->{target_node}: {reason.strip()}")
        self.persist(context)
        return context

    def continue_run(
        self, context: RunContext, repository: str | Path, *,
        develop: Callable[[RunContext, RepositoryTools], None],
        brainstorm: Callable[[RunContext], None] | None = None,
        plan: Callable[[RunContext], None] | None = None,
        verify: Callable[[RunContext], None] | None = None,
        refactor: Callable[[RunContext, RepositoryTools], None] | None = None,
        repair_test: Callable[[RunContext, RepositoryTools], None] | None = None,
        related_tests: list[str] | None = None,
    ) -> RunContext:
        """Continue at ``current_node`` without rescanning or recreating a workspace."""
        if context.status == "awaiting_human":
            return context
        if context.status == "blocked":
            raise ValueError("blocked run requires an explicit unblock decision")
        if context.status != "running":
            raise ValueError(f"status {context.status} cannot continue")
        if context.workspace is None or Path(context.workspace.repository).resolve() != Path(repository).resolve():
            raise ValueError("continuation requires the persisted workspace")
        while context.current_node in {"brainstorming", "planning", "verify"}:
            node = context.current_node
            callback = {"brainstorming": brainstorm, "planning": plan, "verify": verify}[node]
            if callback is None:
                raise ValueError(f"{node} callback is required to continue")
            callback(context)
            if node == "brainstorming":
                context.current_node = "planning"
                self.persist(context, node)
            elif node == "planning":
                self.record_plan(context, revised=self._revision_exists(context, "plan", context.plan_version))
            else:
                self.record_verify(context, revised=self._revision_exists(context, "verify", context.verify_version))
                if context.current_node == "verify":
                    return context

        tools = RepositoryTools(context.workspace, self._verified_plan_paths(context))
        tools.operations = list(context.tool_operations)
        while context.current_node in {"development", "testing", "refactor"}:
            if context.current_node == "development":
                develop(context, tools)
                context.tool_operations = list(tools.operations)
                context.current_node = "testing"
                self.persist(context, "development")
            if context.current_node == "testing":
                result, executions = TestRunner(repository, context.repository_profile).run(related_tests)
                context.test_result = result
                context.test_executions.extend(executions)
                if not result.passed:
                    output = executions[-1].output if executions else "; ".join(result.details)
                    feedback = classify_failure(output, exit_code=executions[-1].exit_code if executions else 1)
                    self.route_feedback(context, feedback, "testing")
                    if context.current_node not in {"development", "testing"}:
                        return context
                    context.iteration += 1
                    if context.iteration >= context.max_iterations:
                        context.status = "failed"
                        self.persist(context, "testing")
                        return context
                    if feedback.category == "test_error":
                        if repair_test is None:
                            context.status = "blocked"
                            context.errors.append("test_error requires a repair_test callback")
                            self.persist(context, "testing")
                            return context
                        repair_test(context, tools)
                        context.tool_operations = list(tools.operations)
                        self.persist(context, "testing")
                    continue
                context.current_node = "refactor"
                self.persist(context, "testing")
            if context.current_node == "refactor":
                if refactor is None:
                    context.refactor_result = RefactorResult(False, "未发现有价值且不改变行为的重构项")
                else:
                    refactor(context, tools)
                    if context.refactor_result is None:
                        raise ValueError("Refactor callback must set context.refactor_result")
                context.tool_operations = list(tools.operations)
                result, executions = TestRunner(repository, context.repository_profile).run(related_tests)
                context.test_result = result
                context.test_executions.extend(executions)
                if not result.passed:
                    context.current_node = "development"
                    self.persist(context, "refactor")
                    continue
                context.status = "completed"
                context.current_node = "archive"
                context.resume_allowed = False
                self.persist(context, "refactor")
                archive_run(context, self.runs_root, baseline_diff(context.workspace))
        return context

    def _revision_exists(self, context: RunContext, kind: str, version: int) -> bool:
        return (self.runs_root / context.run_id / f"{kind}-r{version}.yaml").is_file()
