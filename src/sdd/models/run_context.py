"""The single context object passed through all M1 nodes."""

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
    max_iterations: int = 1
    errors: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
