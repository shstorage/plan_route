"""Atomic local storage for deterministic routing and validation reports."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel

RESULTS_DIR = Path(__file__).resolve().parents[3] / "data" / "results"


def save_report(report: BaseModel, request: BaseModel) -> BaseModel:
    """Store a report under a content-derived request ID in a fixed directory."""
    payload = json.dumps(
        request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    result_id = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    stored = report.model_copy(update={"result_id": result_id})
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    target = RESULTS_DIR / f"{result_id}.json"
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=RESULTS_DIR, suffix=".tmp", delete=False
        ) as stream:
            temporary = stream.name
            stream.write(stored.model_dump_json(indent=2))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)
    return stored
