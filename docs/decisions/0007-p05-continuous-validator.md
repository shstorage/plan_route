# P05: continuous route validation and report storage

The validator reads the EngineeringProject AABBs and the supplied centreline
points. It does not use the voxel grid or compiled masks. Segment-to-AABB
Euclidean distance is minimized exactly by splitting the segment parameter at
box-face crossings and minimizing the resulting quadratic on each interval.
This checks full segments, including the short port-to-grid connectors.

The insulated pipe radius is outer diameter / 2 plus insulation thickness.
Physical obstacle and KEEP_OUT contact at that radius is a violation.
MIN_CLEARANCE requires centreline-to-target distance of at least that radius
plus the approved surface clearance; equality passes. The building envelope
must remain strictly inside the building. Distances and coordinates are metres.

The routing endpoint compiles rules, searches, then validates the resulting
polyline. It reports `SUCCESS` only for zero violations. Search failures retain
their own statuses. A manually supplied invalid route is a completed validation
with HTTP 200 and `INVALID_ROUTE`; an automatically generated invalid route is
reported as a routing failure with HTTP 409 and `INVALID_ROUTE`.

Reports include applied rule IDs, source for rule violations, a SHA-256 hash of
the canonical project snapshot plus pipe ID, and a SHA-256 request ID. API
reports are atomically written to the fixed `data/results/` directory. They
contain only synthetic benchmark inputs and are ignored by version control.
