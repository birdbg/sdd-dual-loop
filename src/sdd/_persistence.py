"""Shared strict YAML persistence helpers for M3."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import yaml


def validate_run_id(run_id: str) -> None:
    if (
        not isinstance(run_id, str)
        or not run_id
        or run_id in {".", ".."}
        or Path(run_id).is_absolute()
        or "/" in run_id
        or "\\" in run_id
        or Path(run_id).name != run_id
    ):
        raise ValueError("run_id must be one safe non-empty path component")


def plain(value: Any) -> Any:
    if is_dataclass(value):
        return {key: plain(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def atomic_yaml(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            yaml.safe_dump(plain(value), stream, allow_unicode=True, sort_keys=False)
            stream.flush()
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return path


def load_mapping(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        try:
            value = yaml.safe_load(stream)
        except yaml.YAMLError as error:
            raise ValueError(f"invalid YAML in {path.name}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a YAML object")
    return value


def require_exact_fields(data: dict[str, Any], fields: dict[str, type | tuple[type, ...]]) -> None:
    missing = [name for name in fields if name not in data]
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))
    for name, expected in fields.items():
        value = data[name]
        # bool is an int subclass and must not satisfy integer fields.
        if expected is int and (not isinstance(value, int) or isinstance(value, bool)):
            raise ValueError(f"field {name} must be int")
        if expected is bool and not isinstance(value, bool):
            raise ValueError(f"field {name} must be bool")
        if expected not in {int, bool} and not isinstance(value, expected):
            raise ValueError(f"field {name} has invalid type")
