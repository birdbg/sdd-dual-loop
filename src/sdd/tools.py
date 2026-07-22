"""Auditable repository-local file tools used by development."""

from __future__ import annotations

from pathlib import Path

from sdd.models import ToolOperation, WorkspaceRecord
from sdd.workspace import baseline_diff


class ToolBoundaryError(ValueError):
    pass


class RepositoryTools:
    def __init__(self, workspace: WorkspaceRecord, allowed_paths: list[str] | None = None) -> None:
        self.workspace = workspace
        self.root = Path(workspace.repository).resolve(strict=True)
        self.allowed_paths = set(allowed_paths or [])
        self.operations: list[ToolOperation] = []
        self.originals: dict[str, str] = {}

    def list_files(self, path: str = ".") -> list[str]:
        target = self._resolve(path, require_exists=True)
        if not target.is_dir():
            raise ToolBoundaryError(f"not a directory: {path}")
        return sorted(
            p.relative_to(self.root).as_posix() for p in target.rglob("*")
            if p.is_file() and ".git" not in p.relative_to(self.root).parts
        )

    def read_file(self, path: str) -> str:
        target = self._resolve(path, require_exists=True)
        if not target.is_file():
            raise ToolBoundaryError(f"not a file: {path}")
        return target.read_text(encoding="utf-8")

    def search_text(self, query: str, path: str = ".") -> list[tuple[str, int, str]]:
        if not query:
            raise ValueError("query must not be empty")
        target = self._resolve(path, require_exists=True)
        files = [target] if target.is_file() else target.rglob("*")
        matches: list[tuple[str, int, str]] = []
        for file in files:
            if not file.is_file() or ".git" in file.relative_to(self.root).parts:
                continue
            try:
                lines = file.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            matches.extend(
                (file.relative_to(self.root).as_posix(), number, line)
                for number, line in enumerate(lines, 1) if query in line
            )
        return matches

    def write_file(self, path: str, content: str, iteration: int = 0) -> None:
        target = self._resolve(path, require_exists=True, write=True)
        if not target.is_file():
            raise ToolBoundaryError(f"not a file: {path}")
        relative = target.relative_to(self.root).as_posix()
        self.originals.setdefault(relative, target.read_text(encoding="utf-8"))
        target.write_text(content, encoding="utf-8")
        self.operations.append(ToolOperation(relative, "write", iteration))

    def create_file(self, path: str, content: str, iteration: int = 0) -> None:
        target = self._resolve(path, require_exists=False, write=True)
        if target.exists():
            raise ToolBoundaryError(f"file already exists: {path}")
        if not target.parent.is_dir():
            raise ToolBoundaryError("parent directory must already exist")
        target.write_text(content, encoding="utf-8")
        self.operations.append(ToolOperation(target.relative_to(self.root).as_posix(), "create", iteration))

    def show_diff(self) -> str:
        return baseline_diff(self.workspace)

    def _resolve(self, path: str, *, require_exists: bool, write: bool = False) -> Path:
        raw = Path(path)
        if raw.is_absolute() or ".." in raw.parts:
            raise ToolBoundaryError("path must be repository-relative without '..'")
        candidate = self.root.joinpath(raw)
        try:
            resolved = candidate.resolve(strict=require_exists)
        except FileNotFoundError as error:
            raise ToolBoundaryError(f"path does not exist: {path}") from error
        if not resolved.is_relative_to(self.root):
            raise ToolBoundaryError("path escapes repository root")
        if not require_exists:
            parent = candidate.parent.resolve(strict=True)
            if not parent.is_relative_to(self.root):
                raise ToolBoundaryError("path escapes repository root")
            resolved = parent / candidate.name
        relative = resolved.relative_to(self.root).as_posix()
        if write and self.allowed_paths and relative not in self.allowed_paths:
            raise ToolBoundaryError(f"path is outside the verified plan: {relative}")
        return resolved
