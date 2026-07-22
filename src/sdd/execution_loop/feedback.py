"""Deterministically classify failed execution and route it inside the dual loop."""

from sdd.models import ExecutionFeedback


def classify_failure(output: str, *, exit_code: int = 1) -> ExecutionFeedback:
    text = output.lower()
    blocked = ("permission denied", "no space left", "connection refused", "could not resolve", "no module named 'pytest'", "command not found")
    if any(marker in text for marker in blocked):
        return ExecutionFeedback("blocked", "archive", output, "stop until the environment is available")
    if any(marker in text for marker in ("acceptance criteria conflict", "ambiguous requirement", "specification unclear")):
        return ExecutionFeedback("spec_ambiguous", "change_spec", output, "request a manual Change Spec")
    if any(marker in text for marker in ("outside verified plan", "plan omission", "missing planned file")):
        return ExecutionFeedback("plan_omission", "planning", output, "revise Plan and Verify before development")
    if any(marker in text for marker in ("fixture ", "error at setup", "collection error", "test file error")):
        return ExecutionFeedback("test_error", "testing", output, "repair the test or fixture and rerun")
    return ExecutionFeedback("code_error", "development", output, f"repair implementation and rerun (exit {exit_code})")
