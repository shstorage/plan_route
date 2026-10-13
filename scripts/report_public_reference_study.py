"""Export descriptive P10D tables/figures without re-running the solver."""

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch", type=Path)
    args = parser.parse_args()
    batch = args.batch
    summary = json.loads((batch / "summary.json").read_text(encoding="utf-8"))
    comparisons = json.loads((batch / "comparisons.json").read_text(encoding="utf-8"))
    with (batch / "runs.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    figures = batch / "figures"
    figures.mkdir(exist_ok=True)
    resolutions = sorted({float(row["resolution_m"]) for row in rows}, reverse=True)
    totals = [
        Counter(row["status"] for row in rows if float(row["resolution_m"]) == r)
        for r in resolutions
    ]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    x = list(range(len(resolutions)))
    valid = [c["SUCCESS"] for c in totals]
    rejected = [c["INVALID_ROUTE"] for c in totals]
    axes[0].bar(x, valid, label="Final valid", color="#24775e")
    axes[0].bar(
        x, rejected, bottom=valid, label="Rejected: self clearance", color="#cb7848"
    )
    axes[0].set_xticks(x, [f"{r:g} m" for r in resolutions])
    axes[0].set_ylabel("Runs")
    axes[0].set_title("Final route outcomes")
    axes[0].legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2)
    for i, total in enumerate(totals):
        axes[0].text(
            i,
            sum(total.values()) + 1,
            f"{valid[i]}/{sum(total.values())} valid",
            ha="center",
            fontsize=9,
        )
    axes[0].set_ylim(0, max(sum(c.values()) for c in totals) * 1.2)
    axes[1].bar(
        ["Normalized\ninvalid", "Normalized\nvalid"],
        [summary["normalized_false_valid"], summary["normalized_false_invalid"]],
        color=["#b03f3f", "#cb7848"],
    )
    axes[1].set_ylabel("Misclassified analytical inputs")
    axes[1].set_title("Boundary semantics: false valid / false invalid")
    axes[1].set_ylim(0, max(3, summary["normalized_false_invalid"] + 1))
    axes[1].text(
        0.5,
        0.85,
        "10 invalid + 14 valid probes\n"
        "Two height-equality inputs rejected\n"
        "Split/unsplit inputs are correlated",
        transform=axes[1].transAxes,
        ha="center",
        fontsize=9,
    )
    fig.savefig(figures / "outcomes.png", dpi=220)
    fig.savefig(figures / "outcomes.pdf")
    plt.close(fig)
    table = []
    for item in comparisons:
        if item["algorithm"] != "astar":
            continue
        table.append(
            {
                "case_id": item["case_id"],
                "resolution_m": item["resolution_m"],
                "after_status": item["after_status"],
                "old_path_under_new_rules": item["old_path_under_new_rules"]["status"],
                "delta_length_m": item.get("delta_length_m"),
                "delta_bends": item.get("delta_bends"),
                "delta_objective": item.get("delta_objective"),
            }
        )
    evidence = {
        "batch_id": batch.name,
        "summary": summary,
        "astar_pairs": table,
        "increased_cost_with_valid_old_path_pairs": sum(
            item["finite_valid_cost_pair"]
            and item.get("delta_objective", 0) > 0
            and item["old_path_under_new_rules"]["status"] == "VALID"
            for item in comparisons
        ),
        "input_file_sha256": {
            name: hashlib.sha256((batch / name).read_bytes()).hexdigest()
            for name in (
                "runs.csv",
                "summary.json",
                "comparisons.json",
                "gold_probes.json",
                "sources.json",
                "source.zip",
            )
        },
    }
    with (batch / "report_evidence.json").open("w", encoding="utf-8") as stream:
        json.dump(evidence, stream, indent=2)
        stream.write("\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
