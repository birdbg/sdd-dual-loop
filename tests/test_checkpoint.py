from pathlib import Path
import yaml
import pytest

from sdd.checkpoint import load_checkpoint, save_checkpoint
from sdd.models import RunContext


def test_checkpoint_round_trip_is_atomic(tmp_path: Path) -> None:
    context = RunContext("run-1", "input", status="running", current_node="testing", resume_allowed=True)
    before = (context.status, context.current_node, context.resume_allowed)
    saved = save_checkpoint(context, tmp_path)
    assert load_checkpoint("run-1", tmp_path) == saved
    assert not (tmp_path / "run-1" / "checkpoint.yaml.tmp").exists()
    assert (context.status, context.current_node, context.resume_allowed) == before
    context.iteration = 2
    save_checkpoint(context, tmp_path)
    assert load_checkpoint("run-1", tmp_path).iteration == 2


@pytest.mark.parametrize("run_id", ["", ".", "..", "a/b", "a\\b", "/tmp/x"])
def test_checkpoint_rejects_unsafe_run_id(tmp_path: Path, run_id: str) -> None:
    with pytest.raises(ValueError):
        save_checkpoint(RunContext(run_id, "x"), tmp_path)


def test_checkpoint_rejects_missing_and_malformed_data(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_checkpoint("missing", tmp_path)
    directory = tmp_path / "bad"
    directory.mkdir()
    path = directory / "checkpoint.yaml"
    path.write_text("- list\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_checkpoint("bad", tmp_path)
    path.write_text(yaml.safe_dump({"run_id": "bad"}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing"):
        load_checkpoint("bad", tmp_path)
