from pathlib import Path
import pytest

from sdd.models import Plan, RunContext, Spec, VerifyResult
from sdd.versioning import save_plan_revision, save_spec_revision, save_verify_revision


def test_revisions_are_sequential_immutable_and_linked(tmp_path: Path) -> None:
    context = RunContext("versions", "x")
    context.spec = Spec(["r1"])
    first = save_spec_revision(context, tmp_path)
    assert save_spec_revision(context, tmp_path) == first
    context.spec = Spec(["changed same number"])
    with pytest.raises(ValueError, match="different content"):
        save_spec_revision(context, tmp_path)
    context.spec_version, context.spec = 3, Spec(["r3"])
    with pytest.raises(ValueError, match="skip"):
        save_spec_revision(context, tmp_path)
    context.spec_version, context.spec = 2, Spec(["r2"])
    save_spec_revision(context, tmp_path)
    context.plan = Plan([], spec_revision=2, revision=1)
    save_plan_revision(context, tmp_path)
    context.verify_result = VerifyResult(True, spec_revision=2, plan_revision=1, revision=1)
    save_verify_revision(context, tmp_path)


def test_plan_and_verify_reject_stale_links(tmp_path: Path) -> None:
    context = RunContext("links", "x", spec_version=2)
    context.plan = Plan()
    with pytest.raises(ValueError, match="Plan"):
        save_plan_revision(context, tmp_path)
    context.verify_result = VerifyResult(True)
    with pytest.raises(ValueError, match="Verify"):
        save_verify_revision(context, tmp_path)
