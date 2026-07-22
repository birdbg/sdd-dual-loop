from dataclasses import replace
from pathlib import Path

import pytest

from sdd.models import TaskRecord
from sdd.task_registry import TaskRegistry, TaskRegistryError


def task(name: str, status: str = "queued") -> TaskRecord:
    return TaskRecord(name, f"run-{name}", "/repo", f"/trees/{name}", f"sdd/{name}", "abc",
                      status=status, created_at="2026-01-01T00:00:00+00:00")


def test_register_query_list_and_atomic_write(tmp_path: Path) -> None:
    registry = TaskRegistry(tmp_path / "runs" / "tasks.yaml")
    registry.register_task(task("one"))
    assert registry.get_task("one").run_id == "run-one"
    first = registry.list_tasks()
    second = registry.list_tasks()
    first[0].status = "cancelled"
    assert second[0].status == "queued"
    assert not (registry.path.parent / "tasks.yaml.tmp").exists()


@pytest.mark.parametrize("field", ["task_id", "run_id", "worktree_path", "branch"])
def test_duplicate_identities_rejected(tmp_path: Path, field: str) -> None:
    registry = TaskRegistry(tmp_path / "tasks.yaml")
    one, two = task("one"), task("two")
    setattr(two, field, getattr(one, field))
    registry.register_task(one)
    with pytest.raises(TaskRegistryError, match=f"duplicate {field}"):
        registry.register_task(two)


def test_status_and_transition_are_strict(tmp_path: Path) -> None:
    registry = TaskRegistry(tmp_path / "tasks.yaml")
    with pytest.raises(TaskRegistryError, match="unknown"):
        registry.register_task(task("bad", "paused"))
    registry.register_task(task("one"))
    with pytest.raises(TaskRegistryError, match="invalid.*transition"):
        registry.update_task(replace(task("one"), status="running"))
    registry.update_task(replace(task("one"), status="starting"))
    registry.update_task(replace(task("one"), status="running"))
    registry.update_task(replace(task("one"), status="completed"))
    with pytest.raises(TaskRegistryError, match="invalid.*transition"):
        registry.update_task(replace(task("one"), status="running"))


def test_corrupt_yaml_and_unknown_fields_are_rejected(tmp_path: Path) -> None:
    registry = TaskRegistry(tmp_path / "tasks.yaml")
    registry.path.write_text("tasks: [\n", encoding="utf-8")
    with pytest.raises(TaskRegistryError, match="cannot load"):
        registry.list_tasks()
    registry.path.write_text("tasks:\n  - task_id: x\n    extra: true\n", encoding="utf-8")
    with pytest.raises(TaskRegistryError, match="unknown fields"):
        registry.list_tasks()
