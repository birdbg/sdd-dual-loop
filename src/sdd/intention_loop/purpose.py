"""Translate the development requirement into a Purpose artifact."""

from collections.abc import Callable
from importlib.resources import files
from typing import Any

import yaml

from sdd.models import Purpose, RunContext

Completion = Callable[[str], str]


class PurposeNode:
    """Run the fixed Purpose prompt against one shared context."""

    def __init__(self, complete: Completion) -> None:
        self._complete = complete

    def run(self, context: RunContext) -> RunContext:
        if context.current_node != "purpose":
            raise ValueError(
                f"Purpose node cannot run from {context.current_node!r}"
            )

        prompt = _build_prompt(context.input)

        try:
            context.purpose = _parse_purpose(self._complete(prompt))
        except Exception as error:
            context.status = "failed"
            context.errors.append(f"purpose: {error}")
            raise

        context.current_node = "brainstorming"
        context.status = "running"
        context.history.append("purpose:completed")
        return context


def _build_prompt(requirement: str) -> str:
    template = (
        files("sdd.prompts").joinpath("purpose.md").read_text(encoding="utf-8")
    )
    return f"{template}\n\n## 本次输入\n\n{requirement.strip()}\n"


def _parse_purpose(raw_output: str) -> Purpose:
    data: Any = yaml.safe_load(raw_output)
    if not isinstance(data, dict):
        raise ValueError("Purpose output must be a YAML object")

    statement = data.get("statement")
    success_criteria = data.get("success_criteria")
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("Purpose.statement must be a non-empty string")
    if not isinstance(success_criteria, list) or not all(
        isinstance(item, str) and item.strip() for item in success_criteria
    ):
        raise ValueError("Purpose.success_criteria must be a list of strings")

    return Purpose(
        statement=statement.strip(),
        success_criteria=[item.strip() for item in success_criteria],
    )
