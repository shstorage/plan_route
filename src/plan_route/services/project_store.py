"""Versioned, atomic storage for validated EngineeringProject documents."""

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from pydantic import Field

from plan_route.models.engineering import EngineeringProject
from plan_route.models.geometry import ContractModel
from plan_route.services.compiler import project_fingerprint

PROJECTS_DIR = Path(__file__).resolve().parents[3] / "data" / "projects"
_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_STORE_LOCK = RLock()


class StoredProject(ContractModel):
    project_id: str
    schema_version: str
    revision: int = Field(ge=1)
    updated_at: datetime
    document_hash: str
    project: EngineeringProject


class ProjectNotFoundError(FileNotFoundError):
    pass


def _project_path(project_id: str) -> Path:
    if not _ID_PATTERN.fullmatch(project_id):
        raise ValueError("project_id must contain only letters, digits, '_' or '-'")
    directory = PROJECTS_DIR.resolve()
    path = directory / f"{project_id}.json"
    if path.resolve().parent != directory:
        raise ValueError("project_id resolves outside the project directory")
    return path


def load_project(project_id: str) -> StoredProject:
    """Load and revalidate one project, including its content hash."""
    path = _project_path(project_id)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        saved = StoredProject.model_validate(raw)
    except FileNotFoundError as error:
        raise ProjectNotFoundError(f"project {project_id} was not found") from error
    normalized_hash = project_fingerprint(saved.project)
    if saved.document_hash != normalized_hash:
        # Verify the old exact stored payload before supplying new optional defaults.
        old_hash = hashlib.sha256(
            json.dumps(raw["project"], sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        if saved.document_hash != old_hash:
            raise ValueError(f"stored project {project_id} failed integrity validation")
        saved = saved.model_copy(update={"document_hash": normalized_hash})
    if (
        saved.project_id != project_id
        or saved.project.project_id != project_id
        or saved.schema_version != saved.project.schema_version
        or saved.document_hash != normalized_hash
    ):
        raise ValueError(f"stored project {project_id} failed integrity validation")
    return saved


def save_project(project: EngineeringProject) -> StoredProject:
    """Increment revision and atomically replace the fixed project JSON file."""
    path = _project_path(project.project_id)
    with _STORE_LOCK:
        try:
            previous = load_project(project.project_id)
            revision = previous.revision + 1
        except ProjectNotFoundError:
            revision = 1
        saved = StoredProject(
            project_id=project.project_id,
            schema_version=project.schema_version,
            revision=revision,
            updated_at=datetime.now(timezone.utc),
            document_hash=project_fingerprint(project),
            project=project,
        )
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=PROJECTS_DIR,
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = stream.name
                stream.write(
                    json.dumps(
                        saved.model_dump(mode="json"),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
        return saved
