"""P10C counterfactual comparisons and explicit source/object/segment audits."""

import csv
import hashlib
import json
from collections import defaultdict
from math import dist, isclose, sqrt
from pathlib import Path
from statistics import median

from plan_route.models.benchmark import BenchmarkCase, BenchmarkConfig, BenchmarkRun
from plan_route.services.benchmark_statistics import cluster_interval
from plan_route.services.compiler import compile_constraints
from plan_route.services.path_validator import validate_path


def _hash(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _physical(case: BenchmarkCase) -> dict:
    data = case.project.model_dump(mode="json")
    data.pop("constraints")
    return data


def trace_validation(case: BenchmarkCase, points: list[tuple]) -> dict:
    """Audit actual violation links, including the reported geometric segment."""
    report = validate_path(case.project, case.pipe_id, tuple(points))
    rules = {rule.id: rule for rule in case.project.constraints}
    targets = {
        item.id: item.shape for item in [*case.project.obstacles, *case.project.zones]
    }
    pipe = next(item for item in case.project.pipes if item.id == case.pipe_id)
    radius = (
        pipe.outer_diameter_m / 2
        + pipe.insulation_thickness_m
        + pipe.clearance_margin_m
    )
    links = []
    for violation in report.violations:
        if violation.rule_id is None and violation.code not in {
            "KEEP_OUT",
            "MIN_CLEARANCE",
        }:
            continue
        rule = rules.get(violation.rule_id)
        index = violation.segment_index
        segment = points[index : index + 2]
        measured, required = None, None
        shape = targets.get(violation.object_id)
        # Independent AABB algebra for this suite's axis-parallel rule violations.
        # Diagonal endpoint connectors never approach its central Zone.
        if shape is not None and rule is not None and len(segment) == 2:
            start, end = segment
            if sum(abs(a - b) > 1e-9 for a, b in zip(start, end)) <= 1:
                measured = sqrt(
                    sum(
                        max(low - max(a, b), min(a, b) - high, 0) ** 2
                        for a, b, low, high in zip(start, end, shape.min_m, shape.max_m)
                    )
                )
                required = radius + (rule.parameters.distance_m or 0)
        geometry_matches = bool(
            measured is not None
            and required is not None
            and isclose(measured, violation.measured_distance_m, abs_tol=1e-8)
            and isclose(required, violation.required_distance_m, abs_tol=1e-8)
            and (
                measured <= required + 1e-9
                if violation.code == "KEEP_OUT"
                else measured < required - 1e-9
            )
        )
        complete = bool(
            rule is not None
            and rule.approval_is_current
            and rule.status == "approved"
            and case.pipe_id in rule.scope.pipe_ids
            and violation.object_id in rule.scope.target_ids
            and violation.source == rule.source
            and len(segment) == 2
            and violation.code == rule.type.value
            and geometry_matches
        )
        links.append(
            {
                **violation.model_dump(mode="json"),
                "segment_m": segment,
                "definition_revision": rule.definition_revision if rule else None,
                "content_sha256": rule.content_sha256() if rule else None,
                "independent_axis_distance_m": measured,
                "geometry_matches": geometry_matches,
                "complete": complete,
            }
        )
    return {
        "report": report.model_dump(mode="json"),
        "rule_violation_links": links,
        "expected_links": len(links),
        "complete_links": sum(link["complete"] for link in links),
    }


def audit_run(case: BenchmarkCase, run: BenchmarkRun) -> dict:
    compilation = compile_constraints(case.project, case.pipe_id)
    rules = {rule.id: rule for rule in case.project.constraints}
    expected = (
        sorted(
            rule.id
            for rule in rules.values()
            if case.pipe_id in rule.scope.pipe_ids
            and rule.status == "approved"
            and rule.approval_is_current
        )
        if compilation.status == "SUCCESS"
        else []
    )
    records = []
    for rule_id in run.report.applied_rule_ids:
        rule = rules.get(rule_id)
        impact = next(
            (item for item in compilation.impacts if item.rule_id == rule_id), None
        )
        complete = bool(
            rule is not None
            and impact is not None
            and rule.approval_is_current
            and rule.approved_content_sha256 == rule.content_sha256()
            and rule.status == "approved"
            and case.pipe_id in rule.scope.pipe_ids
            and impact.source == rule.source
            and set(impact.target_ids) == set(rule.scope.target_ids)
        )
        records.append(
            {
                "rule_id": rule_id,
                "complete": complete,
                "definition": rule.model_dump(mode="json") if rule else None,
                "target_ids": list(impact.target_ids) if impact else [],
                "affected_cells_count": impact.affected_cells_count if impact else None,
                "newly_blocked_cells_count": impact.newly_blocked_cells_count
                if impact
                else None,
            }
        )
    own = trace_validation(case, run.report.points_m) if run.report.points_m else None
    return {
        "case_id": case.case_id,
        "run_id": run.run_id,
        "input_sha256": run.input_sha256,
        "expected_applied_rule_ids": expected,
        "actual_applied_rule_ids": run.report.applied_rule_ids,
        "applied_set_matches": (
            set(expected)
            == set(run.report.applied_rule_ids)
            == set(compilation.applied_rule_ids)
        ),
        "expected_links": len(expected),
        "complete_links": sum(record["complete"] for record in records),
        "applied_rule_links": records,
        "own_path_validation": own,
    }


def vertex_distance(a: list[tuple], b: list[tuple]) -> float | None:
    """Symmetric vertex-to-polyline maximum, NOT continuous Hausdorff distance."""
    if len(a) < 2 or len(b) < 2:
        return None

    def point_segment(point, start, end):
        vector = [y - x for x, y in zip(start, end)]
        squared = sum(value * value for value in vector)
        if not squared:
            return dist(point, start)
        parameter = max(
            0,
            min(
                1,
                sum((p - s) * value for p, s, value in zip(point, start, vector))
                / squared,
            ),
        )
        return dist(point, [s + parameter * value for s, value in zip(start, vector)])

    return max(
        max(
            min(point_segment(point, start, end) for start, end in zip(y, y[1:]))
            for point in x
        )
        for x, y in ((a, b), (b, a))
    )


def compare_pair(
    before: BenchmarkCase, after: BenchmarkCase, old: BenchmarkRun, new: BenchmarkRun
) -> dict:
    if _physical(before) != _physical(after) or before.pipe_id != after.pipe_id:
        raise ValueError(
            "rule comparison requires identical physical inputs and resolution"
        )
    if old.algorithm != new.algorithm:
        raise ValueError("rule comparison requires the same algorithm")
    old_rules = {
        rule.id: rule.model_dump(mode="json") for rule in before.project.constraints
    }
    new_rules = {
        rule.id: rule.model_dump(mode="json") for rule in after.project.constraints
    }
    changed = sorted(
        key
        for key in old_rules.keys() | new_rules.keys()
        if old_rules.get(key) != new_rules.get(key)
    )
    if changed != sorted(after.changed_rule_ids):
        raise ValueError("intervention metadata does not match changed rules")
    a, b = old.report, new.report
    comparable = all(
        report.status == "SUCCESS"
        and report.search_mode == "EXACT_GRID"
        and report.optimality_guarantee == "GRID_OBJECTIVE_EXCLUDING_SELF_CLEARANCE"
        and report.cost_breakdown is not None
        for report in (a, b)
    )
    comp_a, comp_b = (
        compile_constraints(case.project, case.pipe_id) for case in (before, after)
    )
    masks_available = comp_a.grid is not None and comp_b.grid is not None
    if masks_available:
        # Set differences use the full union, independent of per-rule processing order.
        mask_a = comp_a.grid.rule_cells - comp_a.grid.obstacle_cells
        mask_b = comp_b.grid.rule_cells - comp_b.grid.obstacle_cells
        added, removed = len(mask_b - mask_a), len(mask_a - mask_b)
    else:
        added, removed = None, None
    forward = trace_validation(after, a.points_m) if a.status == "SUCCESS" else None
    reverse = trace_validation(before, b.points_m) if b.status == "SUCCESS" else None
    cost_delta = (
        b.cost_breakdown.total_objective_cost - a.cost_breakdown.total_objective_cost
        if comparable
        else None
    )
    errors = []
    if after.intervention == "ADD_RULE" and changed in (["RULE-KEEP"], ["RULE-SEAL"]):
        links = forward["rule_violation_links"] if forward else []
        if not set(changed) <= {link["rule_id"] for link in links}:
            errors.append("analytic straight crossing lost its expected rule violation")
    if comparable:
        if after.intervention in {"ADD_RULE", "DISTANCE_EDIT"} and cost_delta < -1e-8:
            errors.append("tightening reduced the exact-grid objective")
        if after.intervention == "REMOVE_RULE" and cost_delta > 1e-8:
            errors.append("rule removal increased the exact-grid objective")
    if after.intervention == "SOURCE_EDIT" and (
        a.status != b.status
        or a.points_m != b.points_m
        or added != 0
        or removed != 0
        or cost_delta is None
        or not isclose(cost_delta, 0, abs_tol=1e-9)
    ):
        errors.append("source-only edit changed the executable result")
    if (
        after.intervention == "REMOVE_RULE"
        and changed in (["RULE-KEEP"], ["RULE-DUPLICATE"])
    ) or (after.intervention == "ADD_RULE" and changed == ["RULE-DUPLICATE"]):
        if added != 0 or removed != 0 or cost_delta != 0 or a.points_m != b.points_m:
            errors.append(
                "analytically redundant rule changed the feasible union/result"
            )
    if after.intervention == "APPROVAL_CHECK" and (
        b.status != "UNAPPROVED_RULE"
        or b.search_mode != "NOT_RUN"
        or b.applied_rule_ids
        or b.expanded_states != 0
    ):
        errors.append("unapproved/stale fixture was executed")
    for check in (forward, reverse):
        if check and check["expected_links"] != check["complete_links"]:
            errors.append("incomplete counterfactual source/object/segment links")
    return {
        "before_case_id": before.case_id,
        "after_case_id": after.case_id,
        "before_run_id": old.run_id,
        "after_run_id": new.run_id,
        "scene_id": after.scene_id,
        "seed": after.seed,
        "split": after.split,
        "grid_resolution_m": after.project.routing_config.grid_resolution_m,
        "algorithm": new.algorithm,
        "intervention": after.intervention,
        "changed_rule_ids": changed,
        "physical_input_sha256": _hash(_physical(after)),
        "before_status": a.status,
        "after_status": b.status,
        "exact_success_pair": comparable,
        "objective_delta": cost_delta,
        "length_delta_m": b.cost_breakdown.path_length_m
        - a.cost_breakdown.path_length_m
        if comparable
        else None,
        "bend_delta": b.bend_count - a.bend_count if comparable else None,
        "path_changed": a.points_m != b.points_m if comparable else None,
        "symmetric_vertex_distance_m": vertex_distance(a.points_m, b.points_m)
        if comparable
        else None,
        "union_added_cells": added,
        "union_removed_cells": removed,
        "before_path_under_after_rules": forward,
        "after_path_under_before_rules": reverse,
        "rule_definition_changes": [
            {"rule_id": key, "before": old_rules.get(key), "after": new_rules.get(key)}
            for key in changed
        ],
        "failures": errors,
    }


def analyse_changes(
    cases: list[BenchmarkCase], runs: list[BenchmarkRun], config: BenchmarkConfig
) -> tuple[dict, list[dict], list[dict]]:
    by_case = {case.case_id: case for case in cases}
    groups = defaultdict(list)
    failures = []
    audits = []
    for run in runs:
        case = by_case[run.case_id]
        groups[(run.case_id, run.algorithm)].append(run)
        audit = audit_run(case, run)
        audits.append(audit)
        own = audit["own_path_validation"]
        if (
            not audit["applied_set_matches"]
            or audit["expected_links"] != audit["complete_links"]
            or (own and own["expected_links"] != own["complete_links"])
        ):
            failures.append(f"incomplete run trace: {run.run_id}")
    for (case_id, algorithm), items in groups.items():
        signatures = {
            _hash(
                {
                    "status": item.report.status,
                    "points": item.report.points_m,
                    "cost": item.report.cost_breakdown.__dict__
                    if item.report.cost_breakdown
                    else None,
                    "mode": item.report.search_mode,
                    "rules": item.report.applied_rule_ids,
                }
            )
            for item in items
        }
        if len(signatures) != 1:
            failures.append(f"nondeterministic repetitions: {case_id}/{algorithm}")
        if len(items) != config.repeats or {item.repeat for item in items} != set(
            range(1, config.repeats + 1)
        ):
            failures.append(f"missing/duplicate repetitions: {case_id}/{algorithm}")
    comparisons = []
    for case in cases:
        for algorithm in config.algorithms:
            if (case.case_id, algorithm) not in groups:
                failures.append(f"missing runs: {case.case_id}/{algorithm}")
                continue
            if not case.comparison_parent_id:
                continue
            parent = by_case[case.comparison_parent_id]
            before = groups.get((parent.case_id, algorithm), [])
            after = groups[(case.case_id, algorithm)]
            if not before:
                continue
            pair = compare_pair(parent, case, before[0], after[0])
            pair["before_run_ids"] = [item.run_id for item in before]
            pair["after_run_ids"] = [item.run_id for item in after]
            pair["median_total_ms_before"] = median(
                item.report.timings.total_ms for item in before
            )
            pair["median_total_ms_after"] = median(
                item.report.timings.total_ms for item in after
            )
            comparisons.append(pair)
            failures.extend(
                f"{case.case_id}/{algorithm}: {error}" for error in pair["failures"]
            )
    strata = defaultdict(lambda: defaultdict(list))
    for pair in comparisons:
        if pair["objective_delta"] is not None:
            key = (
                pair["split"],
                pair["grid_resolution_m"],
                pair["algorithm"],
                pair["intervention"],
                tuple(pair["changed_rule_ids"]),
            )
            strata[key][pair["seed"]].append(pair["objective_delta"])
    statistics = []
    for key, values in sorted(strata.items()):
        split, resolution, algorithm, intervention, rule_ids = key
        statistics.append(
            {
                "split": split,
                "grid_resolution_m": resolution,
                "algorithm": algorithm,
                "intervention": intervention,
                "changed_rule_ids": rule_ids,
                **cluster_interval(values, config.bootstrap_resamples, config.seed),
            }
        )
    links = sum(audit["expected_links"] for audit in audits)
    complete = sum(audit["complete_links"] for audit in audits)
    counter_checks = [
        pair[name]
        for pair in comparisons
        for name in ("before_path_under_after_rules", "after_path_under_before_rules")
        if pair[name] is not None
    ]
    violation_links = sum(check["expected_links"] for check in counter_checks)
    summary = {
        "contract": "p10c_rule_interventions_v1",
        "failures": failures,
        "physical_scene_count": len({case.scene_id for case in cases}),
        "comparison_count": len(comparisons),
        "exact_success_pairs": sum(pair["exact_success_pair"] for pair in comparisons),
        "status_transitions": sorted(
            {f"{pair['before_status']}->{pair['after_status']}" for pair in comparisons}
        ),
        "applied_trace": {
            "expected_links": links,
            "complete_links": complete,
            "coverage": complete / links if links else None,
        },
        "counterfactual_trace": {
            "expected_links": violation_links,
            "complete_links": sum(check["complete_links"] for check in counter_checks),
            "checks_without_rule_violations": sum(
                not check["expected_links"] for check in counter_checks
            ),
        },
        "objective_delta_statistics": statistics,
        "limitations": [
            "Controlled synthetic single-pipe family; "
            "not a general causal or design-validity proof.",
            "Repetitions/resolutions are not independent physical samples; "
            "evaluation has two seed clusters.",
            "Finite deltas include only successful EXACT_GRID pairs; "
            "other states remain explicit with null deltas.",
            "Vertex distance samples vertices, "
            "not the exact continuous Hausdorff distance.",
            "Applied rules or ordered newly-blocked counts alone "
            "do not establish causal influence.",
            "Trace coverage audits fixture links, not completeness of "
            "external regulations or authenticated review.",
        ],
    }
    return summary, comparisons, audits


def write_changes(
    batch: Path,
    cases: list[BenchmarkCase],
    runs: list[BenchmarkRun],
    config: BenchmarkConfig,
) -> dict:
    summary, comparisons, audits = analyse_changes(cases, runs, config)
    for name, data in (
        ("change_statistics.json", summary),
        ("change_comparisons.json", comparisons),
        ("traceability_audit.json", audits),
    ):
        with (batch / name).open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
    excluded = {
        "before_path_under_after_rules",
        "after_path_under_before_rules",
        "rule_definition_changes",
        "failures",
    }
    rows = [
        {
            key: json.dumps(value) if isinstance(value, list) else value
            for key, value in pair.items()
            if key not in excluded
        }
        for pair in comparisons
    ]
    with (batch / "change_metrics.csv").open(
        "x", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# P10C controlled rule changes",
        "",
        f"Physical scenes: {summary['physical_scene_count']}; "
        f"comparisons: {len(comparisons)}.",
        "",
        "| Split | Grid m | Algorithm | Intervention / rule | Mean objective delta "
        "| 95% seed-cluster interval | Scenes / clusters |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in summary["objective_delta_statistics"]:
        interval = (
            f"{row['ci_low']:.3f}, {row['ci_high']:.3f}"
            if row["ci_low"] is not None
            else "Not estimated"
        )
        lines.append(
            f"| {row['split']} | {row['grid_resolution_m']} | {row['algorithm']} "
            f"| {row['intervention']} / {','.join(row['changed_rule_ids'])} "
            f"| {row['mean']:.3f} | {interval} "
            f"| {row['n_scenes']} / {row['n_seed_clusters']} |"
        )
    lines.extend(
        [
            "",
            f"Applied-rule trace: {summary['applied_trace']}",
            "",
            f"Counterfactual violation trace: {summary['counterfactual_trace']}",
            "",
            "Status transitions: " + ", ".join(summary["status_transitions"]),
            "",
            "All finite deltas are same-algorithm comparisons. "
            "A*/Dijkstra timing comparison is P10B.",
            "",
            *summary["limitations"],
            "",
            "See change_comparisons.json for path revalidation "
            "and source/object/segment evidence.",
        ]
    )
    (batch / "change_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _figure(batch, summary["objective_delta_statistics"])
    return summary


def _figure(batch: Path, statistics: list[dict]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = [
        row
        for row in statistics
        if row["split"] == "evaluation"
        and row["algorithm"] == "astar"
        and row["grid_resolution_m"] == 1.0
    ]
    figure, axes = plt.subplots(figsize=(10, 5))
    axes.bar(range(len(rows)), [row["mean"] for row in rows])
    axes.set_xticks(
        range(len(rows)),
        [f"{row['intervention']}\n{','.join(row['changed_rule_ids'])}" for row in rows],
        rotation=25,
        ha="right",
        fontsize=8,
    )
    axes.axhline(0, color="black", linewidth=0.7)
    axes.set_ylabel("Mean exact-grid objective delta")
    axes.set_title(
        "Controlled rule interventions: evaluation, A*, 1 m\n"
        "Successful pairs only; descriptive synthetic results"
    )
    figure.tight_layout()
    directory = batch / "figures"
    directory.mkdir(exist_ok=True)
    for extension in ("png", "pdf"):
        figure.savefig(directory / f"rule_change_objective.{extension}", dpi=180)
    plt.close(figure)
