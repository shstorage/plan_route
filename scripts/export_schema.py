"""Export the P01 EngineeringProject JSON Schema from the Pydantic source."""

import json
from pathlib import Path

from plan_route.models.engineering import EngineeringProject


def main() -> None:
    target = (
        Path(__file__).resolve().parents[1]
        / "docs/schema/engineering_project_v1.schema.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(
        EngineeringProject.model_json_schema(),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
    target.write_text(content + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
