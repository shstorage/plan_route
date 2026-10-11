# P04: approved hard-rule compilation

Only rules scoped to the selected pipe are compiled. A relevant rule that is not
approved makes compilation fail closed with `UNAPPROVED_RULE`; the compiler does
not silently drop it. A rule scoped only to another pipe has no effect.

The physical obstacle mask remains separate from `rule_cells`. `KEEP_OUT`
expands a Zone AABB by the insulated pipe radius. `MIN_CLEARANCE` expands its
target AABB by that radius plus the approved distance in metres, measured from
the insulated pipe surface to the target surface. A closed cell/AABB touch
blocks the cell. This is deliberately conservative at grid resolution.

Each rule records its source and both covered interior cells and newly blocked
cells. New cells exclude physical obstacles and cells claimed by earlier rules;
rules are processed by ID for deterministic counts. A compiled grid is tied to
the exact EngineeringProject JSON by a SHA-256 fingerprint, so stale rule masks
cannot be passed to the solver after the project changes.

Port cells blocked by a rule are `RULE_CONFLICT`, distinct from an invalid
physical port cell. A valid compilation that leaves no route returns `NO_PATH`
from the solver. The independent continuous-geometry validator is P05 work.
