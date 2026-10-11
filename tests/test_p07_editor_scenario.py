"""P07 synthetic wall relocation scenario consumed by the 2D editor."""

from plan_route.api.projects import load_demo_project
from plan_route.models.engineering import EngineeringProject
from plan_route.models.results import RouteStatus, ValidationStatus
from plan_route.services.routing import route_project


def test_relocating_demo_wall_changes_valid_route():
    original = load_demo_project()
    before = route_project(original, "PIPE-101")
    data = original.model_dump(mode="json")
    # Equivalent to moving the 7 m tall wall's plan top-left to (5, 9) m.
    data["obstacles"][0]["shape"]["min_m"] = [5, 2, 0]
    data["obstacles"][0]["shape"]["max_m"] = [5.5, 9, 4]
    edited = EngineeringProject.model_validate(data)
    after = route_project(edited, "PIPE-101")

    assert before.status is after.status is RouteStatus.SUCCESS
    assert before.validation.status is after.validation.status is ValidationStatus.VALID
    assert before.points_m != after.points_m
    assert after.cost_breakdown.path_length_m < before.cost_breakdown.path_length_m
    assert before.scenario_hash != after.scenario_hash
