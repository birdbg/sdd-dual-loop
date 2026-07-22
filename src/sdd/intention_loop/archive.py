"""Write a complete and truthful M2 run archive outside the target repository."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import yaml

from sdd.models import Archive, RunContext


def archive_run(context: RunContext, runs_root: str | Path, code_diff: str = "") -> Archive:
    if not context.run_id or Path(context.run_id).name != context.run_id or context.run_id in {".", ".."}:
        raise ValueError("run_id must be one safe path component")
    destination = Path(runs_root).resolve() / context.run_id
    destination.mkdir(parents=True, exist_ok=False)
    markdown = {
        "input.md": context.input,
        "purpose.md": _markdown(context.purpose),
        "brainstorming.md": _markdown(context.brainstorm_result),
        "refactor.md": _markdown(context.refactor_result),
        "archive.md": f"# Run {context.run_id}\n\nStatus: `{context.status}`\n",
    }
    yamls = {
        "repository-profile.yaml": context.repository_profile,
        "spec.yaml": context.spec,
        "plan.yaml": context.plan,
        "verify.yaml": context.verify_result,
        "workspace.yaml": context.workspace,
        "tool-operations.yaml": context.tool_operations,
        "test-result.yaml": {"result": context.test_result, "executions": context.test_executions},
        "feedback.yaml": context.feedback,
    }
    for name, value in markdown.items():
        (destination / name).write_text(value.rstrip() + "\n", encoding="utf-8")
    for name, value in yamls.items():
        (destination / name).write_text(yaml.safe_dump(_plain(value), allow_unicode=True, sort_keys=False), encoding="utf-8")
    (destination / "code-diff.patch").write_text(code_diff, encoding="utf-8")
    artifact = Archive(str(destination), f"M2 run ended with {context.status}")
    context.archive = artifact
    return artifact


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _plain(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _markdown(value: Any) -> str:
    if value is None:
        return ""
    return "```yaml\n" + yaml.safe_dump(_plain(value), allow_unicode=True, sort_keys=False).rstrip() + "\n```"
