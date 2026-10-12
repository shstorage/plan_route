"""Execute P10A/P10B/P10C, preserving every run in the uv-installed package."""

import argparse
import json
from pathlib import Path

from plan_route.models.benchmark import BenchmarkConfig
from plan_route.services.benchmark import ROOT, run_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synthetic pilot/comparison/changes benchmark"
    )
    parser.add_argument("--config", type=Path, default=ROOT / "benchmarks/pilot.json")
    parser.add_argument(
        "--seed",
        type=int,
        help="Override pilot translation or comparison execution-order seed",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "data/benchmarks")
    args = parser.parse_args()
    config_data = json.loads(args.config.read_text(encoding="utf-8"))
    if args.seed is not None:
        config_data["seed"] = args.seed
    config = BenchmarkConfig.model_validate(config_data)
    batch = run_benchmark(config, args.output)
    summary = json.loads((batch / "summary.json").read_text(encoding="utf-8"))
    print(json.dumps({"output": str(batch), **summary}, ensure_ascii=False, indent=2))
    return (
        1
        if (
            summary["failed_runs"]
            or summary["probe_failures"]
            or summary.get("analysis", {}).get("failures")
        )
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
