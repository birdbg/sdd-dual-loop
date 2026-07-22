"""Human-only Spec change boundary."""

from pathlib import Path

from sdd.checkpoint import save_checkpoint
from sdd.models import RunContext, Spec, SpecChange
from sdd.state_store import save_run_context
from sdd.versioning import save_spec_change, save_spec_revision


def apply_spec_change(
    context: RunContext, reason: str, changes: list[str], approved_by: str,
    runs_root: str | Path, *,
    remove_requirements: list[str] | None = None,
    replace_requirements: dict[str, str] | None = None,
    add_acceptance_criteria: list[str] | None = None,
    remove_acceptance_criteria: list[str] | None = None,
    replace_acceptance_criteria: dict[str, str] | None = None,
) -> RunContext:
    if context.status != "awaiting_human":
        raise ValueError("Spec change requires awaiting_human status")
    if context.current_node != "change_spec":
        raise ValueError("Spec change requires the change_spec boundary")
    if context.spec is None:
        raise ValueError("Spec change requires an existing Spec")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason must be non-empty")
    if not isinstance(changes, list) or not changes:
        raise ValueError("changes must be non-empty")
    if any(not isinstance(item, str) or not item.strip() for item in changes):
        raise ValueError("every change must be non-empty")
    if not isinstance(approved_by, str) or not approved_by.strip():
        raise ValueError("approved_by must be explicitly provided")
    if len(context.spec_changes) >= context.max_spec_revisions:
        raise ValueError(f"maximum of {context.max_spec_revisions} human Spec revisions reached")

    # The human boundary itself guarantees the old revision exists before any
    # in-memory mutation, including when callers did not persist r1 earlier.
    save_spec_revision(context, runs_root)

    number = len(context.spec_changes) + 1
    expected_ids = [f"SC-{index:03d}" for index in range(1, number)]
    if [item.change_id for item in context.spec_changes] != expected_ids:
        raise ValueError("existing SpecChange ids are not stable and continuous")
    previous = context.spec_version
    if previous != number:
        raise ValueError("Spec revision and SpecChange history are inconsistent")
    remove_requirements = remove_requirements or []
    replace_requirements = replace_requirements or {}
    add_acceptance_criteria = add_acceptance_criteria or []
    remove_acceptance_criteria = remove_acceptance_criteria or []
    replace_acceptance_criteria = replace_acceptance_criteria or {}
    change = SpecChange(
        change_id=f"SC-{number:03d}", reason=reason.strip(),
        changes=[item.strip() for item in changes], previous_spec_version=previous,
        new_spec_version=previous + 1, approved_by=approved_by.strip(), status="approved",
        add_requirements=[item.strip() for item in changes],
        remove_requirements=remove_requirements,
        replace_requirements=replace_requirements,
        add_acceptance_criteria=add_acceptance_criteria,
        remove_acceptance_criteria=remove_acceptance_criteria,
        replace_acceptance_criteria=replace_acceptance_criteria,
    )
    # Preserve the previous object and immutable revision file.
    context.spec = Spec(
        requirements=_revise(context.spec.requirements, change.add_requirements,
                             change.remove_requirements, change.replace_requirements),
        acceptance_criteria=_revise(context.spec.acceptance_criteria,
                                    change.add_acceptance_criteria,
                                    change.remove_acceptance_criteria,
                                    change.replace_acceptance_criteria),
    )
    context.spec_version = change.new_spec_version
    context.spec_changes.append(change)
    # Intent derived from the previous Spec must never cross the human boundary.
    context.plan = None
    context.verify_result = None
    context.current_node = "brainstorming"
    context.status = "running"
    context.last_completed_node = "change_spec"
    context.resume_allowed = True
    save_spec_change(change, context.run_id, runs_root)
    save_spec_revision(context, runs_root)
    save_checkpoint(context, runs_root)
    save_run_context(context, runs_root)
    return context


def _revise(values: list[str], additions: list[str], removals: list[str], replacements: dict[str, str]) -> list[str]:
    missing = (set(removals) | set(replacements)) - set(values)
    if missing:
        raise ValueError("cannot revise missing Spec entries: " + ", ".join(sorted(missing)))
    revised = [replacements.get(item, item) for item in values if item not in removals]
    revised.extend(additions)
    if any(not isinstance(item, str) or not item.strip() for item in revised):
        raise ValueError("Spec entries must be non-empty strings")
    return revised
