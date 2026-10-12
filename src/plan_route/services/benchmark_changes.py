"""P10C controlled rule interventions on fixed synthetic physical scenes."""

from copy import deepcopy
from datetime import datetime, timezone
from random import Random

from plan_route.models.benchmark import BenchmarkCase, BenchmarkConfig
from plan_route.models.constraints import Constraint, ConstraintStatus, RuleApproval
from plan_route.models.engineering import EngineeringProject
from plan_route.models.results import RouteStatus
from plan_route.services.benchmark_cases import pilot_cases
from plan_route.services.benchmark_scenes import analytic_witness_clear, explicit_graph


def fixture_approval(data: dict, previous: Constraint | None = None) -> dict:
    """Deterministic fixture declaration, never a production approval workflow."""
    rule = Constraint.model_validate(data)
    event = RuleApproval(
        definition_revision=rule.definition_revision,
        content_sha256=rule.content_sha256(),
        approved_by="synthetic-p10c-fixture",
        approved_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
    )
    return rule.model_copy(
        update={
            "status": ConstraintStatus.APPROVED,
            "approved_content_sha256": event.content_sha256,
            "approved_by": event.approved_by,
            "approved_at": event.approved_at.isoformat(),
            "approval_history": [
                *(previous.approval_history if previous else []),
                event,
            ],
        }
    ).model_dump(mode="json")


def _rule(rule_id: str, target: str, distance: float | None = None) -> dict:
    return fixture_approval(
        {
            "id": rule_id,
            "type": "KEEP_OUT" if distance is None else "MIN_CLEARANCE",
            "severity": "hard",
            "scope": {"pipe_ids": ["PIPE-101"], "target_ids": [target]},
            "parameters": {}
            if distance is None
            else {
                "distance_m": distance,
                "distance_basis": "insulated_pipe_surface_to_target_surface",
            },
            "source": {
                "source_type": "synthetic_assumption",
                "document_id": "P10C-FIXTURE",
                "document_revision": "1",
                "clause_id": rule_id,
                "evidence_text": "Synthetic controlled study assumption only.",
            },
            "status": "draft",
        }
    )


def _variants() -> list[tuple[str, str | None, str | None, list[str], list[dict]]]:
    keep = _rule("RULE-KEEP", "ZONE")
    clearance = _rule("RULE-CLEAR", "ZONE", 0.25)
    edited = deepcopy(clearance)
    edited["parameters"]["distance_m"] = 1.25
    edited["definition_revision"] = 2
    edited = fixture_approval(edited, Constraint.model_validate(clearance))
    source_edit = deepcopy(edited)
    source_edit["source"].update(
        document_revision="2",
        evidence_text="Revised citation; executable value unchanged.",
    )
    source_edit["definition_revision"] = 3
    source_edit = fixture_approval(source_edit, Constraint.model_validate(edited))
    duplicate = _rule("RULE-DUPLICATE", "ZONE")
    full = [keep, source_edit, duplicate]
    draft = deepcopy(keep)
    draft["status"] = "draft"
    stale = deepcopy(edited)
    stale["parameters"]["distance_m"] = 1.5  # Deliberately NOT reapproved.
    variants = [
        ("base", None, None, [], []),
        ("keep", "base", "ADD_RULE", ["RULE-KEEP"], [keep]),
        ("clear", "keep", "ADD_RULE", ["RULE-CLEAR"], [keep, clearance]),
        ("increase", "clear", "DISTANCE_EDIT", ["RULE-CLEAR"], [keep, edited]),
        ("source", "increase", "SOURCE_EDIT", ["RULE-CLEAR"], [keep, source_edit]),
        ("duplicate", "source", "ADD_RULE", ["RULE-DUPLICATE"], full),
    ]
    for rule in full:
        variants.append(
            (
                f"remove-{rule['id'].lower()}",
                "duplicate",
                "REMOVE_RULE",
                [rule["id"]],
                [item for item in full if item["id"] != rule["id"]],
            )
        )
    return [
        *variants,
        (
            "sealed",
            "base",
            "ADD_RULE",
            ["RULE-SEAL"],
            [_rule("RULE-SEAL", "ZONE-SEAL")],
        ),
        ("draft", "keep", "APPROVAL_CHECK", ["RULE-KEEP"], [draft]),
        ("stale", "increase", "APPROVAL_CHECK", ["RULE-CLEAR"], [keep, stale]),
    ]


def change_cases(config: BenchmarkConfig) -> list[BenchmarkCase]:
    cases = []
    for split, seeds in (
        ("development", config.scene_seeds),
        ("evaluation", config.evaluation_seeds),
    ):
        for seed in seeds:
            data = pilot_cases(0)[0].project.model_dump(mode="json")
            data["project_id"] = f"SYNTH-CHANGE-{seed}"
            data["coordinate_frame"]["origin_m"] = [0, 0, 0]
            data["building"] = {
                "bounds_m": {"min_m": [0, 0, 0], "max_m": [12, 10, 4]},
                "floors": [{"id": "F1", "z_min_m": 0, "z_max_m": 4}],
            }
            data["obstacles"] = []
            height = Random(seed).uniform(3.1, 4.8)
            data["zones"] = [
                {
                    "id": name,
                    "zone_type": "synthetic",
                    "shape": {"min_m": [5.6, 0, 0], "max_m": [6.4, high, 4]},
                }
                for name, high in (("ZONE", height), ("ZONE-SEAL", 10))
            ]
            start, end = (1.5, 1.5, 1.5), (10.5, 1.5, 1.5)
            data["equipment"][0]["ports"][0].update(position_m=start, orientation="+x")
            data["equipment"][1]["ports"][0].update(position_m=end, orientation="-x")
            data["routing_config"]["search_limits"]["max_expansions"] = 200000
            for resolution in config.resolutions_m:
                prefix = f"change-{split}-{seed}-r{resolution:g}"
                for name, parent, intervention, changed, rules in _variants():
                    variant = deepcopy(data)
                    variant["constraints"] = deepcopy(rules)
                    variant["routing_config"]["grid_resolution_m"] = resolution
                    project = EngineeringProject.model_validate(variant)
                    status = (
                        RouteStatus.NO_PATH
                        if name == "sealed"
                        else RouteStatus.UNAPPROVED_RULE
                        if name in {"draft", "stale"}
                        else RouteStatus.SUCCESS
                    )
                    witness = (
                        []
                        if status != RouteStatus.SUCCESS
                        else (
                            [start, end]
                            if name == "base"
                            else [
                                start,
                                (2.5, 1.5, 1.5),
                                (2.5, 8.5, 1.5),
                                (9.5, 8.5, 1.5),
                                (9.5, 1.5, 1.5),
                                end,
                            ]
                        )
                    )
                    if witness and not analytic_witness_clear(project, witness):
                        raise ValueError("P10C analytic witness intersects a target")
                    cases.append(
                        BenchmarkCase(
                            case_id=f"{prefix}-{name}",
                            description=f"Rule variant {name}; same physical scene",
                            project=project,
                            expected_status=status,
                            truth_basis=(
                                "Analytic witness and independent regular graph."
                                if status == RouteStatus.SUCCESS
                                else "Zone spans Y/Z and separates X endpoints."
                                if status == RouteStatus.NO_PATH
                                else "Draft/stale approval must fail before search."
                            ),
                            feasibility_label=(
                                "WITNESS"
                                if status == RouteStatus.SUCCESS
                                else "SEPARATING_WALL"
                                if status == RouteStatus.NO_PATH
                                else "PRECONDITION"
                            ),
                            witness_m=witness,
                            reference_graph=explicit_graph(project),
                            scene_id=f"change-{split}-{seed}",
                            split=split,
                            family="rule_changes",
                            seed=seed,
                            comparison_parent_id=f"{prefix}-{parent}"
                            if parent
                            else None,
                            intervention=intervention,
                            changed_rule_ids=changed,
                            expected_search_mode="NOT_RUN"
                            if status == RouteStatus.UNAPPROVED_RULE
                            else "EXACT_GRID",
                        )
                    )
    return cases
