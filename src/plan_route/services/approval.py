"""Explicit local human declaration bound to a rule's current definition."""

from datetime import datetime, timezone

from plan_route.models.constraints import ConstraintStatus, RuleApproval
from plan_route.models.engineering import EngineeringProject


def approve_rule(
    project: EngineeringProject,
    rule_id: str,
    approved_by: str,
) -> EngineeringProject:
    actor = approved_by.strip()
    if not actor:
        raise ValueError("approval requires a nonempty reviewer name")
    rule = next((item for item in project.constraints if item.id == rule_id), None)
    if rule is None:
        raise ValueError(f"unknown rule ID: {rule_id}")
    revision = rule.definition_revision
    if rule.approval_history and (
        rule.approval_history[-1].content_sha256 != rule.content_sha256()
        and revision <= rule.approval_history[-1].definition_revision
    ):
        revision = rule.approval_history[-1].definition_revision + 1
    changed = rule.model_copy(update={"definition_revision": revision})
    event = RuleApproval(
        definition_revision=revision,
        content_sha256=changed.content_sha256(),
        approved_by=actor,
        approved_at=datetime.now(timezone.utc),
    )
    changed = changed.model_copy(
        update={
            "status": ConstraintStatus.APPROVED,
            "approved_by": actor,
            "approved_at": event.approved_at.isoformat(),
            "approved_content_sha256": event.content_sha256,
            "approval_history": [*rule.approval_history, event],
        }
    )
    return EngineeringProject.model_validate(
        project.model_copy(
            update={
                "constraints": [
                    changed if item.id == rule_id else item
                    for item in project.constraints
                ],
            }
        ).model_dump(mode="json")
    )
