"""Evidence-based discovery for small Python/FastAPI repositories."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from sdd.models import RepositoryProfile

_IGNORED = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules"}


def scan_repository(repository: str | Path, requirement: str = "") -> RepositoryProfile:
    root = Path(repository).resolve(strict=True)
    if not (root / ".git").exists():
        raise ValueError("target must be a Git repository")

    files = sorted(
        p for p in root.rglob("*")
        if p.is_file() and not p.is_symlink() and not any(part in _IGNORED for part in p.relative_to(root).parts)
    )
    rel = {p: p.relative_to(root).as_posix() for p in files}
    py_files = [p for p in files if p.suffix == ".py"]
    tests = [p for p in py_files if "tests" in p.parts or p.name.startswith("test_")]
    dependency = next((name for name in ("pyproject.toml", "requirements.txt", "setup.cfg", "setup.py", "Pipfile") if (root / name).is_file()), None)

    entrypoints: list[str] = []
    routes: list[str] = []
    imports_fastapi = False
    parsed: dict[Path, ast.AST] = {}
    for path in py_files:
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (UnicodeDecodeError, SyntaxError, OSError):
            continue
        parsed[path] = tree
        if re.search(r"(?:from|import)\s+fastapi", text):
            imports_fastapi = True
        if any(
            isinstance(node, ast.Call)
            and ((isinstance(node.func, ast.Name) and node.func.id == "FastAPI")
                 or (isinstance(node.func, ast.Attribute) and node.func.attr == "FastAPI"))
            for node in ast.walk(tree)
        ):
            entrypoints.append(rel[path])
        if "APIRouter" in text or re.search(r"@\w+\.(get|post|put|patch|delete)\s*\(", text):
            routes.append(rel[path])

    source_roots = sorted({
        _source_root(path.relative_to(root)) for path in py_files if path not in tests
    } - {""})
    test_roots = sorted({
        Path(rel[p]).parts[0] if len(Path(rel[p]).parts) > 1 else "." for p in tests
    })
    command = _test_command(root, dependency, bool(tests))
    relevant = _relevant_files(requirement, py_files, rel, set(entrypoints + routes))
    evidence = list(dict.fromkeys(
        ([dependency] if dependency else []) + entrypoints + routes + test_roots
    ))
    unresolved: list[str] = []
    if not entrypoints:
        unresolved.append("FastAPI application entrypoint not found")
    if not tests:
        unresolved.append("test files not found")
    if not command:
        unresolved.append("executable test command not supported by repository evidence")
    return RepositoryProfile(
        language="python" if py_files else "unknown",
        framework="fastapi" if imports_fastapi or entrypoints else "unknown",
        source_roots=source_roots,
        test_roots=test_roots,
        entrypoints=entrypoints,
        route_files=routes,
        relevant_files=relevant,
        dependency_file=dependency,
        test_command=command,
        evidence=evidence,
        unresolved=unresolved,
    )


def _source_root(path: Path) -> str:
    parts = path.parts
    if parts and parts[0] == "src":
        return "src"
    return parts[0] if len(parts) > 1 else "."


def _test_command(root: Path, dependency: str | None, has_tests: bool) -> str | None:
    if not has_tests:
        return None
    if dependency == "pyproject.toml":
        text = (root / dependency).read_text(encoding="utf-8", errors="ignore")
        if "pytest" in text or "[tool.pytest" in text:
            return "python -m pytest -q"
    for name in ("requirements.txt", "requirements-dev.txt", "requirements-test.txt"):
        path = root / name
        if path.is_file() and "pytest" in path.read_text(encoding="utf-8", errors="ignore").lower():
            return "python -m pytest -q"
    if (root / "pytest.ini").exists() or (root / "conftest.py").exists():
        return "python -m pytest -q"
    return None


def _relevant_files(requirement: str, files: list[Path], rel: dict[Path, str], always: set[str]) -> list[str]:
    terms = {t.lower() for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", requirement)}
    terms -= {"add", "the", "and", "with", "from", "fastapi", "endpoint"}
    result = set(always)
    for path in files:
        haystack = rel[path].lower()
        try:
            haystack += "\n" + path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        if terms and any(term in haystack for term in terms):
            result.add(rel[path])
    return sorted(result)
