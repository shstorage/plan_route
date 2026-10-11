import type { Aabb, Point3 } from '../api/client'

/**
 * The only place where world metres become Three.js scene units.
 *
 * World: right-handed, metres, +Z up (EngineeringProject coordinate_frame).
 * Scene: right-handed, metres, +Y up (Three.js convention).
 * Mapping: scene = (x, z, -y). This is a proper rotation (determinant +1),
 * so handedness, lengths and angles are preserved; no scaling or offset is applied.
 */
export type ScenePoint = [number, number, number]

// `0 - v` instead of `-v` so a zero coordinate stays +0 rather than -0.
export function worldToScene(point: Point3): ScenePoint {
  return [point[0], point[2], 0 - point[1]]
}

/** Inverse mapping for tests; never used to read domain data back from meshes. */
export function sceneToWorld(point: ScenePoint): Point3 {
  return [point[0], 0 - point[2], point[1]]
}

/** Scene-space centre and edge lengths of a world AABB. */
export function worldBoxToScene(box: Aabb): { center: ScenePoint; size: ScenePoint } {
  const center: Point3 = [
    (box.min_m[0] + box.max_m[0]) / 2,
    (box.min_m[1] + box.max_m[1]) / 2,
    (box.min_m[2] + box.max_m[2]) / 2,
  ]
  return {
    center: worldToScene(center),
    size: [box.max_m[0] - box.min_m[0], box.max_m[2] - box.min_m[2], box.max_m[1] - box.min_m[1]],
  }
}
