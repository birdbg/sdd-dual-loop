"""The minimal contract implemented by a workflow stage."""

from typing import Protocol

from .context import RunContext


class WorkflowStage(Protocol):
    """Run one sequential stage and return its updated context."""

    def run(self, context: RunContext) -> RunContext: ...
