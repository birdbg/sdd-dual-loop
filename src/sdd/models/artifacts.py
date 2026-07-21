"""Minimal artifacts produced along the M1 path."""

from dataclasses import dataclass, field


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
    completed: bool = False


@dataclass(slots=True)
class Plan:
    tasks: list[Task] = field(default_factory=list)


@dataclass(slots=True)
class VerifyResult:
    approved: bool
    feedback: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CodeChange:
    path: str
    summary: str


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
