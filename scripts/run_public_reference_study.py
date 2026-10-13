"""Run P10D examples without changing existing benchmark suites or UI defaults."""

import argparse
import json
from pathlib import Path

from plan_route.services.benchmark import ROOT
from plan_route.services.public_reference_cases import public_reference_cases
from plan_route.services.public_reference_study import run_public_reference_study


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "data/benchmarks")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--export-examples",
        type=Path,
        help="Export draft EngineeringProject JSON for manual review",
    )
    args = parser.parse_args()
    if args.export_examples:
        args.export_examples.mkdir(parents=True, exist_ok=True)
        for case in public_reference_cases():
            data = case.project.model_dump(mode="json")
            for rule in data["constraints"]:
                rule.update(
                    status="draft",
                    approved_by=None,
                    approved_at=None,
                    approved_content_sha256=None,
                    approval_history=[],
                )
            path = args.export_examples / f"{case.case_id}.json"
            with path.open("x", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            print(path)
        return 0
    batch = run_public_reference_study(args.output, repeats=args.repeats)
    summary = json.loads((batch / "summary.json").read_text(encoding="utf-8"))
    print(json.dumps({"output": str(batch), **summary}, indent=2))
    return int(bool(summary["failures"]))


if __name__ == "__main__":
    raise SystemExit(main())
