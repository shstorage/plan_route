"""Scene-level descriptive statistics and seed-cluster bootstrap artifacts."""

import csv
import json
from collections import defaultdict
from pathlib import Path
from random import Random
from statistics import mean, median

from plan_route.models.benchmark import BenchmarkCase, BenchmarkConfig, BenchmarkRun
from plan_route.services.benchmark_cases import pilot_cases
from plan_route.services.path_validator import validate_path


def cluster_interval(values: dict[int, list[float]], samples: int, seed: int) -> dict:
    """Percentile bootstrap by generator seed, keeping scene families together."""
    flat = [value for cluster in values.values() for value in cluster]
    if not flat:
        return {
            "mean": None,
            "ci_low": None,
            "ci_high": None,
            "n_scenes": 0,
            "n_seed_clusters": 0,
        }
    keys = sorted(values)
    if len(keys) < 2:
        return {
            "mean": mean(flat),
            "ci_low": None,
            "ci_high": None,
            "n_scenes": len(flat),
            "n_seed_clusters": len(keys),
        }
    rng = Random(seed)
    estimates = sorted(
        mean(value for key in rng.choices(keys, k=len(keys)) for value in values[key])
        for _ in range(samples)
    )

    def quantile(fraction):
        index = (len(estimates) - 1) * fraction
        low = int(index)
        return estimates[low] + (
            estimates[min(low + 1, len(estimates) - 1)] - estimates[low]
        ) * (index - low)

    return {
        "mean": mean(flat),
        "ci_low": quantile(0.025),
        "ci_high": quantile(0.975),
        "n_scenes": len(flat),
        "n_seed_clusters": len(keys),
    }


def scene_metrics(
    cases: list[BenchmarkCase], runs: list[BenchmarkRun]
) -> tuple[list[dict], list[str]]:
    by_case = {case.case_id: case for case in cases}
    groups = defaultdict(list)
    for run in runs:
        groups[(run.case_id, run.algorithm)].append(run)
    rows, failures = [], []
    for (case_id, algorithm), items in sorted(groups.items()):
        case = by_case[case_id]
        signatures = {
            json.dumps(
                {
                    "status": run.report.status,
                    "mode": run.report.search_mode,
                    "points": run.report.points_m,
                    "cost": run.report.model_dump(mode="json")["cost_breakdown"],
                },
                sort_keys=True,
            )
            for run in items
        }
        if len(signatures) != 1:
            failures.append(f"nondeterministic result: {case_id}/{algorithm}")
        report = items[0].report
        cost = report.cost_breakdown
        rows.append(
            {
                "case_id": case_id,
                "scene_id": case.scene_id or case_id,
                "split": case.split,
                "seed": case.seed,
                "family": case.family,
                "resolution_m": report.grid_resolution_m,
                "algorithm": algorithm,
                "status": report.status,
                "search_mode": report.search_mode,
                "n_repeats": len(items),
                "known_feasible": case.feasibility_label == "WITNESS",
                "success_fraction": mean(
                    run.report.status == "SUCCESS" for run in items
                ),
                "objective_cost": cost.total_objective_cost if cost else None,
                "path_length_m": cost.path_length_m if cost else None,
                "bend_count": report.bend_count,
                "expanded_states": report.expanded_states,
                "hard_violation_count": len(report.validation.violations)
                if report.validation
                else None,
                "median_total_ms": median(run.report.timings.total_ms for run in items),
                "median_search_ms": median(
                    run.report.timings.search_ms for run in items
                ),
                "min_total_ms": min(run.report.timings.total_ms for run in items),
                "max_total_ms": max(run.report.timings.total_ms for run in items),
                "oracle_status": items[0].reference.status,
                "oracle_cost": items[0].reference.objective_cost,
            }
        )
    return rows, failures


def analyse(
    cases: list[BenchmarkCase], runs: list[BenchmarkRun], config: BenchmarkConfig
) -> tuple[dict, list[dict]]:
    rows, failures = scene_metrics(cases, runs)
    rates, paired, distributions = [], [], []
    # Resolution is held fixed; repeats have already been collapsed to one scene row.
    for split in ("development", "evaluation"):
        for resolution in config.resolutions_m:
            subset = [
                row
                for row in rows
                if row["split"] == split and row["resolution_m"] == resolution
            ]
            for algorithm in config.algorithms:
                eligible = [
                    row
                    for row in subset
                    if row["algorithm"] == algorithm and row["known_feasible"]
                ]
                clusters = defaultdict(list)
                for row in eligible:
                    clusters[row["seed"]].append(row["success_fraction"])
                rates.append(
                    {
                        "split": split,
                        "resolution_m": resolution,
                        "algorithm": algorithm,
                        **cluster_interval(
                            clusters, config.bootstrap_resamples, config.seed
                        ),
                    }
                )
            by_case = defaultdict(dict)
            for row in subset:
                by_case[row["case_id"]][row["algorithm"]] = row
            delta, gaps, a_times, d_times = (
                defaultdict(list),
                [],
                defaultdict(list),
                defaultdict(list),
            )
            for case_id, pair in by_case.items():
                if set(pair) != {"astar", "dijkstra"}:
                    continue
                a, d = pair["astar"], pair["dijkstra"]
                if a["status"] != d["status"]:
                    failures.append(f"algorithm status disagreement: {case_id}")
                if (
                    a["status"] == d["status"] == "SUCCESS"
                    and a["search_mode"] == d["search_mode"] == "EXACT_GRID"
                ):
                    gap = a["objective_cost"] - d["objective_cost"]
                    gaps.append(gap)
                    if abs(gap) > 1e-8:
                        failures.append(f"exact-grid objective disagreement: {case_id}")
                    delta[a["seed"]].append(d["median_total_ms"] - a["median_total_ms"])
                    a_times[a["seed"]].append(a["median_total_ms"])
                    d_times[d["seed"]].append(d["median_total_ms"])
            paired.append(
                {
                    "split": split,
                    "resolution_m": resolution,
                    "metric": "median_total_ms_dijkstra_minus_astar",
                    **cluster_interval(delta, config.bootstrap_resamples, config.seed),
                    "max_absolute_objective_gap": max(map(abs, gaps), default=None),
                    "astar_ms": cluster_interval(
                        a_times, config.bootstrap_resamples, config.seed
                    ),
                    "dijkstra_ms": cluster_interval(
                        d_times, config.bootstrap_resamples, config.seed
                    ),
                }
            )
            for algorithm in config.algorithms:
                for mode in sorted({row["search_mode"] for row in subset}):
                    selected = [
                        row
                        for row in subset
                        if row["algorithm"] == algorithm and row["search_mode"] == mode
                    ]
                    if selected:
                        distributions.append(
                            {
                                "split": split,
                                "resolution_m": resolution,
                                "algorithm": algorithm,
                                "search_mode": mode,
                                "n_cases": len(selected),
                                "status_counts": {
                                    status: sum(
                                        row["status"] == status for row in selected
                                    )
                                    for status in sorted(
                                        {row["status"] for row in selected}
                                    )
                                },
                                "median_of_scene_medians_ms": median(
                                    row["median_total_ms"] for row in selected
                                ),
                                "mean_expanded_states": mean(
                                    row["expanded_states"] for row in selected
                                ),
                            }
                        )
    return {
        "method": (
            "95% percentile bootstrap of generator-seed clusters "
            "after scene-level repeat medians"
        ),
        "bootstrap_resamples": config.bootstrap_resamples,
        "bootstrap_seed": config.seed,
        "caution": (
            "Families sharing a seed stay together. Evaluation has few seed "
            "clusters; intervals are descriptive, not population guarantees."
        ),
        "success_rates": rates,
        "paired_exact_comparisons": paired,
        "distributions": distributions,
        "failures": failures,
        "physical_scene_count": len(
            {case.scene_id for case in cases if case.split != "diagnostic"}
        ),
        "diagnostic_case_count": sum(case.split == "diagnostic" for case in cases),
    }, rows


def _validator_trials() -> list[dict]:
    # Labels are predeclared analytic fixtures, never obtained from validator output.
    from plan_route.services.benchmark import _probes

    records = []
    for case in [pilot_cases(42)[i] for i in (0, 1, 4, 6)]:
        valid = validate_path(case.project, case.pipe_id, tuple(case.witness_m))
        records.append(
            {
                "trial_id": f"{case.case_id}-valid",
                "expected_valid": True,
                "actual_valid": valid.status == "VALID",
                "points_m": case.witness_m,
                "report": valid.model_dump(mode="json"),
            }
        )
        for probe in _probes(case):
            records.append(
                {
                    "trial_id": f"{case.case_id}-{probe['probe_id']}",
                    "expected_valid": False,
                    "actual_valid": probe["report"]["status"] == "VALID",
                    **probe,
                }
            )
    return records


def _plots(batch: Path, stats: dict, rows: list[dict]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    figures = batch / "figures"
    figures.mkdir()

    def save(fig, name):
        fig.tight_layout()
        fig.savefig(figures / f"{name}.png", dpi=220)
        fig.savefig(figures / f"{name}.pdf")
        plt.close(fig)

    comparisons = stats["paired_exact_comparisons"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for index, split in enumerate(("development", "evaluation")):
        selected = [item for item in comparisons if item["split"] == split]
        for algorithm, offset, color in (
            ("astar", -0.17, "#187bcd"),
            ("dijkstra", 0.17, "#e28743"),
        ):
            values = [item[f"{algorithm}_ms"]["mean"] or 0 for item in selected]
            axes[index].bar(
                [i + offset for i in range(len(selected))],
                values,
                width=0.32,
                label=algorithm,
                color=color,
            )
            for i, item in enumerate(selected):
                interval = item[f"{algorithm}_ms"]
                if interval["ci_low"] is not None:
                    axes[index].plot(
                        [i + offset] * 2,
                        [interval["ci_low"], interval["ci_high"]],
                        color="black",
                        linewidth=1,
                    )
        axes[index].set_xticks(
            range(len(selected)), [f"{item['resolution_m']} m" for item in selected]
        )
        axes[index].set_title(split)
        axes[index].set_ylabel("Mean of scene median service time (ms)")
        axes[index].legend()
    save(fig, "paired_service_time")

    fig, ax = plt.subplots(figsize=(8, 4))
    for algorithm, offset in (("astar", -0.15), ("dijkstra", 0.15)):
        rates = [
            item for item in stats["success_rates"] if item["algorithm"] == algorithm
        ]
        ax.bar(
            [i + offset for i in range(len(rates))],
            [item["mean"] or 0 for item in rates],
            width=0.28,
            label=algorithm,
        )
    rates = [
        item
        for item in stats["success_rates"]
        if item["algorithm"] == config_alg(stats)
    ]
    ax.set_xticks(
        range(len(rates)),
        [f"{item['split']}\n{item['resolution_m']} m" for item in rates],
    )
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Valid paths / scenes with analytic continuous witness")
    ax.legend()
    save(fig, "known_feasible_success")

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for split, marker in (("development", "o"), ("evaluation", "s")):
        selected = [
            row
            for row in rows
            if row["split"] == split
            and row["algorithm"] == "astar"
            and row["status"] == "SUCCESS"
        ]
        axes[0].scatter(
            [row["path_length_m"] for row in selected],
            [row["bend_count"] for row in selected],
            marker=marker,
            label=split,
            alpha=0.65,
        )
        axes[1].scatter(
            [row["expanded_states"] for row in selected],
            [row["median_search_ms"] for row in selected],
            marker=marker,
            label=split,
            alpha=0.65,
        )
    axes[0].set(xlabel="Path length (m)", ylabel="Grid bend count")
    axes[1].set(xlabel="Expanded states", ylabel="Scene median search time (ms)")
    for ax in axes:
        ax.legend()
    save(fig, "path_and_search_distribution")


def config_alg(stats: dict) -> str:
    return stats["success_rates"][0]["algorithm"]


def write_comparison(
    batch: Path,
    cases: list[BenchmarkCase],
    runs: list[BenchmarkRun],
    config: BenchmarkConfig,
) -> dict:
    from plan_route.services.benchmark import _write_json

    stats, rows = analyse(cases, runs, config)
    trials = _validator_trials()
    references = {run.case_id: run.reference.status for run in runs}
    stats["oracle_coverage"] = {
        status: sum(value == status for value in references.values())
        for status in ("PATH", "NO_PATH", "NOT_COMPUTED")
    }
    stats["validator_trials"] = {
        "n": len(trials),
        "false_valid": sum(
            not trial["expected_valid"] and trial["actual_valid"] for trial in trials
        ),
        "false_invalid": sum(
            trial["expected_valid"] and not trial["actual_valid"] for trial in trials
        ),
        "invalid_trial_count": sum(not trial["expected_valid"] for trial in trials),
        "valid_trial_count": sum(trial["expected_valid"] for trial in trials),
    }
    stats["failures"].extend(
        trial["trial_id"]
        for trial in trials
        if trial["actual_valid"] != trial["expected_valid"]
    )
    _write_json(batch / "validator_trials.json", trials)
    _write_json(batch / "comparison_statistics.json", stats)
    with (batch / "scene_metrics.csv").open(
        "x", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    _plots(batch, stats, rows)
    lines = [
        "# P10B synthetic comparison",
        "",
        stats["method"],
        "",
        stats["caution"],
        "",
        "| Split | Grid (m) | Paired scenes | Dijkstra minus A* (ms) "
        "| 95% cluster interval | Max cost gap |",
        "|---|---:|---:|---:|---|---:|",
    ]
    for item in stats["paired_exact_comparisons"]:
        lines.append(
            f"| {item['split']} | {item['resolution_m']} | {item['n_scenes']} "
            f"| {item['mean']} | [{item['ci_low']}, {item['ci_high']}] "
            f"| {item['max_absolute_objective_gap']} |"
        )
    lines.extend(
        [
            "",
            "Only matched SUCCESS/EXACT_GRID pairs enter the timing/cost comparison.",
            "Continuous-witness success rates include conservative-grid failures. "
            "Repeats and resolutions do not create new physical scenes.",
            "Diagnostic heuristic routes are excluded from exact comparisons. "
            "No physical-space optimality or real-plant compliance is claimed.",
            "See scene_metrics.csv for length/bends/expansions and timing ranges; "
            "runs.csv retains each measurement.",
        ]
    )
    (batch / "comparison_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return {
        "physical_scene_count": stats["physical_scene_count"],
        "diagnostic_case_count": stats["diagnostic_case_count"],
        "failures": stats["failures"],
        "validator_trials": stats["validator_trials"],
    }
