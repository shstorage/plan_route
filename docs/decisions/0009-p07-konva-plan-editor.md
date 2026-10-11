# P07: React Konva floor-plan editor

The 2D editor is a view over the EngineeringProject JSON, not a second data
model. Konva nodes are rebuilt from the domain document on every render and
`stage.toJSON()` is never persisted. Every drag, resize, create, or inspector
edit goes through a pure function in `frontend/src/editor/model.ts` that
returns a new EngineeringProject with metre coordinates, or throws a
user-facing error without changing the document (non-finite values, edges
under 0.1 m, geometry outside the building bounds, unknown IDs, missing
distance or provenance on rules).

Screen pixels and world metres are related only through
`frontend/src/editor/coordinates.ts`: plan X grows right, plan Y grows up, so
the screen y axis is inverted against `bounds_m.max_m[1]`; pan/zoom is a
uniform scale plus offset applied by the Konva stage. Snapping uses
`routing_config.grid_resolution_m` measured from `coordinate_frame.origin_m`.
P08 must reuse these world coordinates instead of reading positions back from
2D or 3D render objects.

A floor shows the shapes and ports whose z range intersects the floor's
`[z_min_m, z_max_m]`; route segments are clipped to that slab before drawing.
Editing an AABB from the plan changes only x/y; z extents stay as stored and
can be edited numerically in the inspector.

Undo/redo stores serialized JSON snapshots (`editor/history.ts`, 50 entries).
Snapshots are small for synthetic projects and make restored states exactly
equal to what would be saved. Editing the raw JSON text resets history, since
that text may be invalid until it is validated again.

Rules created in the editor always start as `draft` with a
`synthetic_assumption` source; the user must set `approved` explicitly. The
editor only warns about unapproved rules; enforcement stays on the server,
which returns `UNAPPROVED_RULE`. Any edit clears the previous route result so a
stale path is never shown over changed geometry.

Konva adds roughly 350 kB to the unsplit bundle (Vite's 500 kB chunk warning).
Code splitting is deferred until the P08 3D viewer settles the final bundle
layout.
