"""String types for node and run state; no separate state object."""

from typing import Literal, TypeAlias

NodeName: TypeAlias = Literal[
    "purpose",
    "brainstorming",
    "planning",
    "verify",
    "development",
    "testing",
    "refactor",
    "archive",
]

RunStatus: TypeAlias = Literal[
    "pending",
    "running",
    "awaiting_human",
    "completed",
    "failed",
]
