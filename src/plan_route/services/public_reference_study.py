"""Retained P10D examples and analytical checks; no regulatory compliance claim."""

import csv
import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from math import isclose
from pathlib import Path
from random import Random
from uuid import uuid4

from plan_route.models.engineering import EngineeringProject
from plan_route.models.results import RouteStatus, ValidationStatus
from plan_route.services.benchmark import ROOT, _environment, _write_json
from plan_route.services.benchmark_changes import fixture_approval
from plan_route.services.compiler import compile_constraints
from plan_route.services.path_validator import validate_path
from plan_route.services.public_reference_cases import (
    PublicReferenceCase,
    authored_witness,
    gold_probes,
    public_reference_cases,
)
from plan_route.services.routing import route_project


def project_variant(case: PublicReferenceCase, variant: str, resolution: float):
    data = case.project.model_dump(mode="json")
    data["routing_config"]["grid_resolution_m"] = resolution
    if variant == "baseline":
        data["constraints"] = []
    elif variant == "source_note":
        rule = data["constraints"][0]
        rule["source"]["evidence_text"] += " Study citation note; geometry unchanged."
        rule["definition_revision"] += 1
        data["constraints"] = [fixture_approval(rule, case.project.constraints[0])]
    elif variant == "draft":
        data["constraints"][0]["status"] = "draft"
    elif variant == "stale":
        data["constraints"][0]["source"]["evidence_text"] += " Unapproved study edit."
    elif variant != "reference":
        raise ValueError(f"unknown variant: {variant}")
    return EngineeringProject.model_validate(data)


def evaluate_probe(case: PublicReferenceCase, probe: dict) -> dict:
    """Compare object/segment/source/distance to an authored analytical oracle."""
    validation = validate_path(probe["project"], "PIPE-101", probe["points_m"])
    rule = probe["project"].constraints[0]
    desired = {
        (rule.id, rule.scope.target_ids[0], segment)
        for segment in probe["expected_rule_segments"]
    }
    actual = {(v.rule_id, v.object_id, v.segment_index) for v in validation.violations}
    evidence_ok = all(
        v.source == rule.source
        and isclose(v.measured_distance_m, probe["expected_distance_m"], abs_tol=1e-8)
        and isclose(v.required_distance_m, probe["expected_required_m"], abs_tol=1e-8)
        for v in validation.violations
    )
    actual_valid = validation.status is ValidationStatus.VALID
    return {
        "probe_id": probe["probe_id"],
        "points_m": probe["points_m"],
        "normalized_valid": probe["normalized_valid"],
        "contract_valid": probe["contract_valid"],
        "actual_valid": actual_valid,
        "contract_matches": actual_valid == probe["contract_valid"],
        "normalized_false_valid": actual_valid and not probe["normalized_valid"],
        "normalized_false_invalid": not actual_valid and probe["normalized_valid"],
        "expected_rule_segments": probe["expected_rule_segments"],
        "expected_distance_m": probe["expected_distance_m"],
        "expected_required_m": probe["expected_required_m"],
        "true_positive_links": len(desired & actual),
        "false_positive_links": len(actual - desired),
        "false_negative_links": len(desired - actual),
        "evidence_matches": evidence_ok,
        "passed": actual_valid == probe["contract_valid"]
        and actual == desired
        and evidence_ok,
        "validation": validation.model_dump(mode="json"),
    }


def run_public_reference_study(
    output: Path, *, repeats: int = 3, resolutions: tuple[float, ...] = (0.5, 0.25)
) -> Path:
    if type(repeats) is not int or not 1 <= repeats <= 20:
        raise ValueError("repeats must be an integer in [1,20]")
    if (
        not resolutions
        or len(set(resolutions)) != len(resolutions)
        or any(value not in {0.5, 0.25} for value in resolutions)
    ):
        raise ValueError("unique .5/.25 m resolutions are supported")
    output.mkdir(parents=True, exist_ok=True)
    batch = output / f"P10D-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex}"
    batch.mkdir(exist_ok=False)
    cases = public_reference_cases()
    config = {
        "contract": "public_reference_examples_v1",
        "repeats": repeats,
        "resolutions_m": resolutions,
        "execution_seed": 20261013,
        "sample_unit": "4 authored scenes, 3 source families; no population inference",
        "approval": "synthetic fixture declaration; no expert endorsement",
    }
    _write_json(batch / "config.json", config)
    _write_json(
        batch / "sources.json",
        json.loads(
            (ROOT / "benchmarks/public_reference_sources.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    environment = _environment(batch)
    environment.update(
        {
            "benchmark_contract": config["contract"],
            "reference_version": "authored_axis_parallel_probes_v1",
        }
    )
    _write_json(batch / "environment.json", environment)
    _write_json(
        batch / "manifest.json",
        {
            "case_ids": [c.case_id for c in cases],
            "planned_runs": len(cases) * len(resolutions) * 3 * 2 * repeats,
            "state_file": "completion.json",
        },
    )
    probes, controls, jobs, witnesses = [], [], [], []
    for case in cases:
        directory = batch / case.case_id
        directory.mkdir()
        metadata = asdict(case)
        metadata.pop("project")
        _write_json(directory / "applicability.json", metadata)
        _write_json(directory / "project.json", case.project.model_dump(mode="json"))
        witness = authored_witness(case)
        witness_validation = validate_path(case.project, "PIPE-101", witness)
        witnesses.append(
            {
                "case_id": case.case_id,
                "points_m": witness,
                "validation": witness_validation.model_dump(mode="json"),
                "passed": witness_validation.status is ValidationStatus.VALID,
                "truth_basis": "Authored axis-parallel detour; "
                "not a solver-generated path. "
                "Geometric argument is recorded in the P10D decision document.",
            }
        )
        for probe in gold_probes(case):
            evaluated = evaluate_probe(case, probe)
            evaluated["case_id"] = case.case_id
            # Preserve endpoint-adjusted canonical input, not just the evaluated label.
            evaluated["project"] = probe["project"].model_dump(mode="json")
            probes.append(evaluated)
        for variant in ("draft", "stale"):
            project = project_variant(case, variant, resolutions[0])
            result = compile_constraints(project, "PIPE-101")
            control = {
                "case_id": case.case_id,
                "variant": variant,
                "project": project.model_dump(mode="json"),
                "status": result.status.value,
                "passed": result.status.value == "UNAPPROVED_RULE",
            }
            controls.append(control)
        for resolution in resolutions:
            for variant in ("baseline", "reference", "source_note"):
                project = project_variant(case, variant, resolution)
                _write_json(
                    directory / f"project-{resolution}-{variant}.json",
                    project.model_dump(mode="json"),
                )
                for repeat in range(repeats):
                    for algorithm in ("astar", "dijkstra"):
                        jobs.append((case, variant, project, repeat + 1, algorithm))
    Random(20261013).shuffle(jobs)
    _write_json(
        batch / "execution_plan.json",
        [
            {
                "case_id": c.case_id,
                "variant": v,
                "resolution_m": p.routing_config.grid_resolution_m,
                "repeat": r,
                "algorithm": a,
            }
            for c, v, p, r, a in jobs
        ],
    )
    rows, reports, failures, route_rejections = [], {}, [], []
    for index, (case, variant, project, repeat, algorithm) in enumerate(jobs):
        report = route_project(project, "PIPE-101", algorithm=algorithm)
        resolution = project.routing_config.grid_resolution_m
        key = (case.case_id, resolution, variant, algorithm, repeat)
        reports[key] = report
        name = f"r{resolution}-{variant}-{algorithm}-{repeat}.json"
        _write_json(batch / case.case_id / name, report.model_dump(mode="json"))
        valid = (
            report.status is RouteStatus.SUCCESS
            and report.validation is not None
            and (report.validation.status is ValidationStatus.VALID)
        )
        if not valid:
            diagnostic = (
                report.status is RouteStatus.INVALID_ROUTE
                and report.validation is not None
                and bool(report.validation.violations)
                and report.points_m[-1] != report.grid_points_m[-1]
                and all(
                    v.code == "SELF_CLEARANCE"
                    and v.segment_index == len(report.points_m) - 2
                    for v in report.validation.violations
                )
            )
            route_rejections.append(
                {
                    "case_id": case.case_id,
                    "file": name,
                    "status": report.status.value,
                    "violation_codes": sorted(
                        {v.code for v in report.validation.violations}
                    )
                    if report.validation
                    else [],
                    "classified_connector_self_clearance": diagnostic,
                }
            )
            if not diagnostic:
                failures.append(f"unclassified route rejection:{case.case_id}/{name}")
        cost = report.cost_breakdown
        rows.append(
            {
                "execution_index": index,
                "case_id": case.case_id,
                "variant": variant,
                "resolution_m": resolution,
                "algorithm": algorithm,
                "repeat": repeat,
                "status": report.status.value,
                "search_mode": report.search_mode.value,
                "path_length_m": cost.path_length_m if cost else None,
                "bend_count": report.bend_count,
                "objective_cost": cost.total_objective_cost if cost else None,
                "total_ms": report.timings.total_ms,
                "passed": valid,
            }
        )
    comparisons = []
    for case in cases:
        for resolution in resolutions:
            project = project_variant(case, "reference", resolution)
            for algorithm in ("astar", "dijkstra"):
                before, after, neutral = [
                    reports[(case.case_id, resolution, v, algorithm, 1)]
                    for v in ("baseline", "reference", "source_note")
                ]
                item = {
                    "case_id": case.case_id,
                    "resolution_m": resolution,
                    "algorithm": algorithm,
                    "before_status": before.status.value,
                    "after_status": after.status.value,
                }
                item["finite_valid_cost_pair"] = (
                    before.status is RouteStatus.SUCCESS
                    and after.status is RouteStatus.SUCCESS
                    and before.cost_breakdown is not None
                    and after.cost_breakdown is not None
                )
                item["old_path_under_new_rules"] = (
                    validate_path(project, "PIPE-101", before.points_m).model_dump(
                        mode="json"
                    )
                    if before.status is RouteStatus.SUCCESS
                    else None
                )
                if item["finite_valid_cost_pair"]:
                    item.update(
                        {
                            "delta_length_m": after.cost_breakdown.path_length_m
                            - before.cost_breakdown.path_length_m,
                            "delta_bends": after.bend_count - before.bend_count,
                            "delta_objective": after.cost_breakdown.total_objective_cost
                            - before.cost_breakdown.total_objective_cost,
                        }
                    )
                item["source_only_same_path_and_cost"] = (
                    after.points_m == neutral.points_m
                    and after.cost_breakdown == neutral.cost_breakdown
                )
                if not item["source_only_same_path_and_cost"]:
                    failures.append(
                        f"source-only geometry changed: {case.case_id}/"
                        f"{resolution}/{algorithm}"
                    )
                comparisons.append(item)
    for case in cases:
        for resolution in resolutions:
            for variant in ("baseline", "reference", "source_note"):
                for repeat in range(1, repeats + 1):
                    pair = [
                        reports[(case.case_id, resolution, variant, algorithm, repeat)]
                        for algorithm in ("astar", "dijkstra")
                    ]
                    if all(
                        p.status is RouteStatus.SUCCESS and p.cost_breakdown
                        for p in pair
                    ) and not isclose(
                        pair[0].cost_breakdown.total_objective_cost,
                        pair[1].cost_breakdown.total_objective_cost,
                        abs_tol=1e-8,
                    ):
                        failures.append(
                            f"paired cost mismatch: {case.case_id}/"
                            f"{resolution}/{variant}/{repeat}"
                        )
    failures.extend(
        f"probe:{p['case_id']}/{p['probe_id']}" for p in probes if not p["passed"]
    )
    failures.extend(
        f"approval:{c['case_id']}/{c['variant']}" for c in controls if not c["passed"]
    )
    failures.extend(f"witness:{w['case_id']}" for w in witnesses if not w["passed"])
    with (batch / "runs.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    _write_json(batch / "gold_probes.json", probes)
    _write_json(batch / "approval_controls.json", controls)
    _write_json(batch / "comparisons.json", comparisons)
    _write_json(batch / "authored_witnesses.json", witnesses)
    _write_json(batch / "route_rejections.json", route_rejections)
    summary = {
        "contract": config["contract"],
        "authored_scenes": len(cases),
        "runs": len(rows),
        "statuses": dict(Counter(row["status"] for row in rows)),
        "valid_runs": sum(row["passed"] for row in rows),
        "route_rejections": len(route_rejections),
        "valid_authored_witnesses": sum(w["passed"] for w in witnesses),
        "finite_valid_cost_pairs": sum(
            c["finite_valid_cost_pair"] for c in comparisons
        ),
        "gold_probes": len(probes),
        "contract_probe_matches": sum(p["passed"] for p in probes),
        "normalized_valid_probes": sum(p["normalized_valid"] for p in probes),
        "normalized_invalid_probes": sum(not p["normalized_valid"] for p in probes),
        "normalized_false_valid": sum(p["normalized_false_valid"] for p in probes),
        "normalized_false_invalid": sum(p["normalized_false_invalid"] for p in probes),
        "link_true_positives": sum(p["true_positive_links"] for p in probes),
        "link_false_positives": sum(p["false_positive_links"] for p in probes),
        "link_false_negatives": sum(p["false_negative_links"] for p in probes),
        "approval_controls": len(controls),
        "failures": failures,
        "limitations": [
            "not legal/compliance ground truth",
            "three source types, four hand-built scenes",
            "boundary and split probes are correlated",
            "A*/Dijkstra share production code",
            "no independent optimal-cost oracle",
            "fine-grid connector self-clearance can reject a route in a feasible scene",
            "no statistical generalization or human-time study",
        ],
    }
    _write_json(batch / "summary.json", summary)
    _write_json(
        batch / "completion.json",
        {"state": "COMPLETE", "passed_contract_checks": not failures},
    )
    return batch
