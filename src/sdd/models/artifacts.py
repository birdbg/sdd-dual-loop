"""Minimal artifacts produced along the M1 path."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass(slots=True)
class Purpose:
    statement: str
    success_criteria: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BrainstormResult:
    summary: str
    ideas: list[str] = field(default_factory=list)
    selected_approach: str = ""


@dataclass(slots=True)
class Spec:
    requirements: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Task:
    task_id: str
    description: str
    allowed_paths: list[str] = field(default_factory=list)
    completed: bool = False


@dataclass(slots=True)
class Plan:
    tasks: list[Task] = field(default_factory=list)
    spec_revision: int = 1
    revision: int = 1


@dataclass(slots=True)
class VerifyResult:
    approved: bool
    feedback: list[str] = field(default_factory=list)
    spec_revision: int = 1
    plan_revision: int = 1
    revision: int = 1


@dataclass(slots=True)
class CodeChange:
    path: str
    summary: str
    content_sha256: str = ""


@dataclass(slots=True)
class TestResult:
    passed: bool
    total: int = 0
    failed: int = 0
    details: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RefactorResult:
    changed: bool
    summary: str = ""


@dataclass(slots=True)
class Archive:
    location: str
    summary: str = ""


@dataclass(slots=True)
class RepositoryProfile:
    """Evidence-backed, task-focused description of a target repository."""

    language: str = "unknown"
    framework: str = "unknown"
    source_roots: list[str] = field(default_factory=list)
    test_roots: list[str] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)
    route_files: list[str] = field(default_factory=list)
    relevant_files: list[str] = field(default_factory=list)
    dependency_file: str | None = None
    test_command: str | None = None
    evidence: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    @property
    def supported(self) -> bool:
        return (
            self.language == "python"
            and self.framework == "fastapi"
            and bool(self.entrypoints)
            and self.test_command is not None
        )


@dataclass(slots=True)
class WorkspaceRecord:
    repository: str
    base_branch: str
    base_commit: str
    work_branch: str
    initial_worktree_clean: bool
    merge: str = "manual"
    push: str = "disabled"


@dataclass(slots=True)
class ToolOperation:
    path: str
    operation: Literal["write", "create"]
    iteration: int
    content_sha256: str = ""


@dataclass(slots=True)
class TestExecution:
    command: list[str]
    cwd: str
    reason: str
    exit_code: int
    output: str


FeedbackCategory = Literal[
    "code_error", "test_error", "plan_omission", "spec_ambiguous", "purpose_conflict", "blocked"
]


@dataclass(slots=True)
class ExecutionFeedback:
    category: FeedbackCategory
    target: Literal["development", "testing", "planning", "change_spec", "purpose", "archive"]
    evidence: str
    decision: str


@dataclass(slots=True)
class Checkpoint:
    run_id: str
    status: str
    current_node: str
    last_completed_node: str | None
    iteration: int
    spec_version: int
    plan_version: int
    verify_version: int
    base_commit: str
    work_branch: str
    resume_allowed: bool


@dataclass(slots=True)
class SpecChange:
    change_id: str
    reason: str
    changes: list[str] = field(default_factory=list)
    previous_spec_version: int = 1
    new_spec_version: int = 1
    approved_by: str = ""
    status: str = "pending"
    add_requirements: list[str] = field(default_factory=list)
    remove_requirements: list[str] = field(default_factory=list)
    replace_requirements: dict[str, str] = field(default_factory=dict)
    add_acceptance_criteria: list[str] = field(default_factory=list)
    remove_acceptance_criteria: list[str] = field(default_factory=list)
    replace_acceptance_criteria: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class RoutingDecision:
    category: str
    source_node: str
    target_node: str
    evidence: str
    decision: str


@dataclass(slots=True)
class TaskRecord:
    """External scheduling record; deliberately not a dual-loop artifact."""

    task_id: str
    run_id: str
    repository: str
    worktree_path: str
    branch: str
    base_commit: str
    status: str = "queued"
    created_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    current_node: str | None = None
    pid: int | None = None
    error: str | None = None
    cleanup_allowed: bool = False
