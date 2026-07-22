"""Explicit feedback routing between the two existing loops."""

from pathlib import Path

from sdd.checkpoint import save_checkpoint
from sdd.models import ExecutionFeedback, RoutingDecision, RunContext
from sdd.state_store import save_run_context

_ROUTES = {
    "code_error": ("development", "running"),
    "test_error": ("testing", "running"),
    "plan_omission": ("planning", "running"),
    "spec_ambiguous": ("change_spec", "awaiting_human"),
    "purpose_conflict": ("purpose", "running"),
    "blocked": ("archive", "blocked"),
}


def route_feedback(
    context: RunContext, feedback: ExecutionFeedback, source_node: str,
    runs_root: str | Path,
) -> RoutingDecision:
    if feedback.category not in _ROUTES:
        raise ValueError(f"unknown feedback category: {feedback.category}")
    target, status = _ROUTES[feedback.category]
    decision = RoutingDecision(
        category=feedback.category, source_node=source_node, target_node=target,
        evidence=feedback.evidence, decision=feedback.decision,
    )
    context.feedback.append(feedback)
    context.routing_history.append(decision)
    context.current_node = target
    context.status = status
    context.resume_allowed = True
    save_checkpoint(context, runs_root)
    save_run_context(context, runs_root)
    return decision
