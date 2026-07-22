"""The single context object passed through all dual-loop nodes."""

from dataclasses import dataclass, field

from sdd.core.state import NodeName, RunStatus

from .artifacts import (
    Archive,
    BrainstormResult,
    CodeChange,
    Plan,
    Purpose,
    RefactorResult,
    Spec,
    TestResult,
    VerifyResult,
    RepositoryProfile,
    WorkspaceRecord,
    ToolOperation,
    TestExecution,
    ExecutionFeedback,
    RoutingDecision,
    SpecChange,
)


@dataclass(slots=True)
class RunContext:
    run_id: str
    input: str
    current_node: NodeName = "purpose"
    status: RunStatus = "pending"

    purpose: Purpose | None = None
    brainstorm_result: BrainstormResult | None = None
    spec: Spec | None = None
    plan: Plan | None = None
    verify_result: VerifyResult | None = None

    code_changes: list[CodeChange] = field(default_factory=list)
    test_result: TestResult | None = None
    refactor_result: RefactorResult | None = None
    archive: Archive | None = None

    iteration: int = 0
    max_iterations: int = 2
    repository_profile: RepositoryProfile | None = None
    workspace: WorkspaceRecord | None = None
    tool_operations: list[ToolOperation] = field(default_factory=list)
    test_executions: list[TestExecution] = field(default_factory=list)
    feedback: list[ExecutionFeedback] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)

    spec_version: int = 1
    plan_version: int = 1
    verify_version: int = 1
    last_completed_node: str | None = None
    resume_allowed: bool = False
    spec_changes: list[SpecChange] = field(default_factory=list)
    routing_history: list[RoutingDecision] = field(default_factory=list)
