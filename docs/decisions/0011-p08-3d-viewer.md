# P08: React Three Fiber 3D viewer and 2D/3D selection sync

The 3D viewer is a second view over the same EngineeringProject JSON as the
2D editor. It never stores anything: meshes are rebuilt from
`buildSceneModel(project, route, pipeId)` (`frontend/src/viewer/scene.ts`)
whenever the document or route changes, and no position is read back from a
mesh into the project.

World metres (+Z up) become Three.js scene units (+Y up) only through
`worldToScene` in `frontend/src/viewer/axes.ts`: `scene = (x, z, -y)`. It is a
proper rotation (determinant +1), so lengths, angles and handedness are
preserved and scene units remain metres. There is no recentering offset; the
camera targets the building centre instead. Tests check the mapping keeps
`x × y = z`, round-trips, and that route cylinder end caps land exactly on
`points_m`.

Selection is lifted to `App` as the editor's existing `{ kind, id }`
`Selection`, so 2D and 3D share object IDs with no translation table. When a
3D click selects an object not drawn on the current 2D floor, the editor
switches to the first floor whose z range shows it (`floorsShowing`). Slabs
cover a whole storey, so they do not take 3D clicks; otherwise an upper slab
would intercept every click on the floor below.

The pipe is drawn as cylinders with the insulated outer radius
(`OD / 2 + insulation`). The pipe's `clearance_margin_m` is a keep-away
envelope used by the grid, compiler and validator, not physical body, so it is
not drawn. The 3D view is visual only; pass/fail stays with the backend
validator.

Camera presets are computed in world coordinates and mapped through
`worldToScene`. The plan view sits a hair south of straight overhead so
OrbitControls' azimuth stays defined and world +Y points up on screen, as in
the 2D plan. The camera is only reset when the building bounds change or the
user asks, not on every edit.

Performance: shared unit box/cylinder/sphere geometries scaled per object,
memoised box components so a selection change re-renders only two boxes, and
`frameloop="demand"`. Instancing is not needed at the synthetic project sizes
(tens of objects). three.js is loaded through `React.lazy`, keeping it in its
own ~960 kB chunk (257 kB gzip) outside the initial bundle; the main chunk
(React + Konva, ~610 kB) still exceeds Vite's 500 kB advisory warning.
