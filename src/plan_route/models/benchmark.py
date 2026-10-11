"""P10A/P10B synthetic experiment contracts; not production design data."""

from typing import Literal

from pydantic import Field, model_validator

from plan_route.models.engineering import EngineeringProject
from plan_route.models.geometry import ContractModel, GridIndex, Point3
from plan_route.models.results import RouteSolveReport, RouteStatus


class BenchmarkConfig(ContractModel):
    suite: Literal["pilot", "comparison"] = "pilot"
    seed: int = Field(default=42, ge=0, le=2**32 - 1, strict=True)
    repeats: int = Field(default=2, ge=1, le=100, strict=True)
    algorithms: list[Literal["astar", "dijkstra"]] = Field(
        default_factory=lambda: ["astar", "dijkstra"], min_length=1, max_length=2
    )
    scene_seeds: list[int] = Field(default_factory=lambda: [11, 23, 42, 71, 101])
    evaluation_seeds: list[int] = Field(default_factory=lambda: [211, 307])
    resolutions_m: list[Literal[1.0, 0.5]] = Field(default_factory=lambda: [1.0, 0.5])
    oracle_max_cells: int = Field(default=600, ge=1, le=5000)
    bootstrap_resamples: int = Field(default=2000, ge=100, le=10000)

    @model_validator(mode="after")
    def check_comparison(self) -> "BenchmarkConfig":
        if self.suite == "comparison":
            if set(self.algorithms) != {"astar", "dijkstra"}:
                raise ValueError("comparison requires both astar and dijkstra")
            for name in ("scene_seeds", "evaluation_seeds", "resolutions_m"):
                values = getattr(self, name)
                if not values or len(set(values)) != len(values):
                    raise ValueError(f"{name} must be nonempty and unique")
            if set(self.scene_seeds) & set(self.evaluation_seeds):
                raise ValueError("development and evaluation seeds must be disjoint")
            if any(
                seed < 0 or seed > 2**32 - 1
                for seed in [*self.scene_seeds, *self.evaluation_seeds]
            ):
                raise ValueError("scene seeds must be unsigned 32-bit integers")
            if (
                7
                * (len(self.scene_seeds) + len(self.evaluation_seeds))
                * len(self.resolutions_m)
                * len(self.algorithms)
                * self.repeats
                > 20000
            ):
                raise ValueError("comparison exceeds the 20000-run limit")
        return self


class ReferenceGraph(ContractModel):
    """Independent regular-edge graph; never derived from solver masks."""

    cells: list[GridIndex]
    start: GridIndex
    goal: GridIndex
    departure: int = Field(ge=0, le=5)
    arrival: int = Field(ge=0, le=5)
    waypoints: list[GridIndex] = Field(default_factory=list)
    waypoint_axes: list[int | None] = Field(default_factory=list)
    length_weight: float = Field(default=1.0, gt=0)
    bend_weight: float = Field(default=2.0, ge=0)
    edge_length_m: float = Field(default=1.0, gt=0, allow_inf_nan=False)
    connector_cost: float = Field(default=0.0, ge=0, allow_inf_nan=False)


class BenchmarkCase(ContractModel):
    case_id: str
    description: str
    project: EngineeringProject
    pipe_id: str = "PIPE-101"
    expected_status: RouteStatus
    truth_basis: str
    feasibility_label: Literal["WITNESS", "SEPARATING_WALL", "PRECONDITION"]
    witness_m: list[Point3] = Field(default_factory=list)
    reference_graph: ReferenceGraph
    max_expansions: int | None = None
    scene_id: str | None = None
    split: Literal["pilot", "development", "evaluation", "diagnostic"] = "pilot"
    family: str = "pilot"
    seed: int | None = None
    expected_search_mode: str | None = None


class ReferenceResult(ContractModel):
    status: Literal["PATH", "NO_PATH", "NOT_COMPUTED"]
    objective_cost: float | None = None
    version: str = "explicit_graph_relaxation_v2"
    domain: str = "EXPLICIT_REGULAR_GRID_EXCLUDING_SELF_CLEARANCE"


class BenchmarkEvaluation(ContractModel):
    passed: bool
    status_matches: bool
    cost_matches_reference: bool | None = None
    witness_validation: str | None = None
    compiled_cells_match_reference: bool | None = None
    errors: list[str] = Field(default_factory=list)


class BenchmarkRun(ContractModel):
    run_id: str
    batch_id: str
    case_id: str
    repeat: int
    algorithm: str
    started_at: str
    completed_at: str
    input_sha256: str
    reference: ReferenceResult
    report: RouteSolveReport
    evaluation: BenchmarkEvaluation
    oracle_ms: float
    execution_index: int = 0
    reference_timing_scope: Literal["run", "case"] = "run"
