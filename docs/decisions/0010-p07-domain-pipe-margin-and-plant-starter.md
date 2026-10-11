# P07 follow-up: domain settings, pipe clearance margin, plant-scale starter

## Pipe clearance margin
`Pipe.clearance_margin_m` (default 0, finite, >= 0) is a user-chosen extra
envelope thickness outside the insulation. `effective_pipe_radius_m` returns
`OD/2 + insulation + margin`, and that single function feeds the voxel grid,
the rule compiler and the independent validator, so all three agree. MIN_CLEARANCE
distances are measured from this envelope; the `distance_basis` name is kept for
compatibility. The field is optional, so existing 1.0.0 documents stay valid and
`schema_version` is unchanged. The margin is a study assumption, never a code value.

## Domain and grid in the editor
The canvas extent is `building.bounds_m`; the editor edits it together with
floor slabs and `routing_config.grid_resolution_m` as domain values. The
frontend mirrors the backend cell-count rounding, warns above 400k cells and
refuses below 0.05 m or above 3M cells to keep the pure-Python solver usable.

## Plant-scale starter
A routing domain of hundreds of metres is a plot-plan scale. A single building
plan is tens of metres, and the current solver is interactive at roughly 0.5 m
over ~60 m. The UI therefore starts from `SYNTH-PLANT-001` (60 x 40 x 12 m,
two floors, 0.5 m grid). The 12 x 10 m demo stays the unit-test fixture. All
geometry and rules are synthetic.

## Masking performance
Masking now visits only cells an AABB can touch (per-axis index windows, then
the same closed-interval test) and builds the interior set per axis, since that
test is separable. Cell bounds and centres come from cached per-axis intervals.
Before/after hashes of interior, obstacle, zone and rule masks, rule impacts,
route points, cost and validation were identical for the demo and every
starter pipe; starter routes went from 14-27 s to 0.3-2.9 s.

Coarse-to-fine (hybrid) search is not implemented; it is a candidate for the
P10 benchmark phase, compared against single-resolution A*.
