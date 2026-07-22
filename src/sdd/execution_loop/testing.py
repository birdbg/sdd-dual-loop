"""Select and execute evidence-backed tests without a shell."""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

from sdd.models import RepositoryProfile, TestExecution, TestResult


class TestRunner:
    def __init__(self, repository: str | Path, profile: RepositoryProfile) -> None:
        self.repository = Path(repository).resolve(strict=True)
        self.profile = profile

    def run(self, related_tests: list[str] | None = None) -> tuple[TestResult, list[TestExecution]]:
        if not self.profile.test_command:
            return TestResult(False, details=["no evidence-backed test command"]), []
        base = shlex.split(self.profile.test_command)
        if not _safe_pytest_command(base):
            return TestResult(False, details=["unsupported or unsafe test command"]), []
        executions: list[TestExecution] = []
        if related_tests:
            for relative in related_tests:
                path = Path(relative)
                if path.is_absolute() or ".." in path.parts or not (self.repository / path).resolve().is_relative_to(self.repository):
                    return TestResult(False, details=[f"test path escapes repository: {relative}"]), []
            command = base + related_tests
            executions.append(self._execute(command, "tests related to the changed files"))
            if executions[-1].exit_code:
                return _result(executions), executions
        executions.append(self._execute(base, "repository configuration and discovered test roots"))
        return _result(executions), executions

    def _execute(self, command: list[str], reason: str) -> TestExecution:
        executable_command = [sys.executable, *command[1:]] if command[0] in {"python", "python3"} else command
        process = subprocess.run(executable_command, cwd=self.repository, text=True, capture_output=True, check=False)
        output = (process.stdout + process.stderr).strip()
        return TestExecution(executable_command, str(self.repository), reason, process.returncode, output)


def _safe_pytest_command(command: list[str]) -> bool:
    return len(command) >= 3 and command[0] in {"python", "python3"} and command[1:3] == ["-m", "pytest"]


def _result(executions: list[TestExecution]) -> TestResult:
    passed = bool(executions) and all(item.exit_code == 0 for item in executions)
    return TestResult(passed, total=len(executions), failed=sum(item.exit_code != 0 for item in executions), details=[item.output for item in executions])
