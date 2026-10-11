# P08b: Ordered mandatory waypoints per pipe

Requested use case: a wall or slab penetration (sleeve) is planned in advance,
e.g. from civil drawings or a rebar scan, and the pipe must cross the wall
there and nowhere else along its route. Users need to define
`start -> 1 -> 2 -> ... -> end`.

## Data

Waypoints are stored directly on the pipe (`Pipe.waypoints`, ordered), each
with `id`, `position_m`, optional `pass_axis` (x/y/z) and optional `note`. The
field is optional and defaults to empty, so existing documents stay valid and
schema version 1.0.0 is unchanged (same approach as `clearance_margin_m`). An
empty list is removed in the editor, so deleting every waypoint restores the
original document. Waypoint IDs are registered in the project-wide ID space.

A separate shared "penetration" object that several pipes reference was
considered and deferred at the user's request. So was the complementary rule
"walls may only be crossed at approved openings" (P09B `ALLOWED_PASSAGE`):
a waypoint says "must pass here", not "may only cross here".

## Search

The A* state becomes `(i, j, k, incoming direction, waypoints visited)`.
Entering the cell of the next waypoint increments the counter; with a
`pass_axis` the arrival direction must lie on that axis and the next move may
not turn, so the pipe runs straight through the point. The goal requires all
waypoints visited. This yields the optimum over the whole sequence, including
bends at waypoints, rather than greedily joining per-leg optima. The heuristic
is the Manhattan distance to the next waypoint plus the Manhattan chain
through the remaining waypoints to the goal, which is admissible and
consistent for 6-neighbour moves; tests compare the cost with Dijkstra.
The reachable state count grows at most linearly with the number of waypoints.

Waypoints are snapped like ports (within half a cell diagonal of a cell
centre). A waypoint in a blocked cell (physical obstacle, inflated building
boundary or approved hard rule) returns `WAYPOINT_BLOCKED` (HTTP 409) instead
of being silently skipped; an unblocked sequence that cannot be satisfied is
`NO_PATH`.

## Validation

The independent validator walks the continuous polyline and requires each
waypoint, in order, to lie within `sqrt(3)/2 x grid_resolution_m` of the
remaining path (`WAYPOINT_MISSED`), and with `pass_axis` the segments meeting
at that point to be parallel to the axis (`WAYPOINT_DIRECTION`). The tolerance
uses the configured resolution only; no solver mask or state is reused.

## UI

Start, end and waypoints of the selected pipe share colours across 2D and 3D
(`editor/roles.ts`: green S, purple E, orange numbered waypoint). Red stays
reserved for validation violations. A sequence strip above the plan shows
`S -> 1 -> ... -> E`; chips select objects and reorder/delete waypoints.

## Self-clearance (added after review of out-and-back sequences)

The exact sequence search does not remember the cells it has used, so a
sequence that goes out to a far waypoint and back can return through the same
or the adjacent cells. With an envelope diameter larger than the cell spacing
the pipe then physically overlaps itself, and the validator did not check this.

Validator: `SELF_CLEARANCE` is reported when two parts of the same centreline
are at most one envelope diameter (2 x effective radius, margin included)
apart while the path between them is longer than pi x radius. The arc bound
exempts elbows and offsets: two points within one diameter that are joined by
a plain bend are at most 2 x sqrt(2) x radius apart along the path, below
pi x radius. Segment pairs use exact closest points of two 3D segments.

Solver: if the optimal sequence has such a conflict, the legs are searched one
at a time; each leg may not enter cells within one diameter of the legs
already laid unless even the shortest continuation from the junction keeps
that pair within the elbow exemption. This is a heuristic: the result is no
longer optimal over the sequence (the message says so) and an earlier leg can
block a later one. If any leg fails, the overlapping optimal route is returned
and the validator reports it, rather than a misleading NO_PATH.
