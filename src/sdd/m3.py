"""Thin M3 lifecycle layer over the existing sequential M2 runner."""

from __future__ import annotations

from pathlib import Path

from sdd.checkpoint import save_checkpoint
from sdd.m2 import M2Runner
from sdd.models import RunContext
from sdd.resume import resume_run
from sdd.state_store import save_run_context
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
