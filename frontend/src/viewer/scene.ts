import type { Aabb, EngineeringProject, Point3, Port, RouteSolveReport } from '../api/client'
import type { Selection } from '../editor/model.ts'
import { worldBoxToScene, worldToScene, type ScenePoint } from './axes.ts'

export type BoxStyle = 'obstacle' | 'slab' | 'keep-out' | 'zone' | 'pending-zone'

export type SceneBox = {
  selection: Selection
  style: BoxStyle
  center: ScenePoint
  size: ScenePoint
}

export type ScenePort = {
  id: string
  center: ScenePoint
  /** End of a short stub showing the port orientation. */
  tip: ScenePoint
  /** Start/end of the selected pipe, otherwise null. */
  role: 'start' | 'end' | null
}

export type SceneWaypoint = {
  id: string
  /** 1-based position in the selected pipe's sequence. */
  order: number
  center: ScenePoint
  /** Ends of a guide line along the required pass axis, if any. */
  axis: [ScenePoint, ScenePoint] | null
}

export type SceneSegment = {
  index: number
  from: ScenePoint
  to: ScenePoint
  center: ScenePoint
  /** Unit direction in scene space. */
  direction: ScenePoint
  length: number
  invalid: boolean
}

export type SceneRoute = {
  pipeId: string
  points: ScenePoint[]
  segments: SceneSegment[]
  /** Insulated outer radius. The pipe's clearance_margin_m is a keep-away envelope, not drawn as body. */
  radius: number
}

export type SceneModel = {
  bounds: { center: ScenePoint; size: ScenePoint }
  boxes: SceneBox[]
  ports: ScenePort[]
  waypoints: SceneWaypoint[]
  route: SceneRoute | null
}

const orientationVector: Record<Port['orientation'], [number, number, number]> = {
  '+x': [1, 0, 0], '-x': [-1, 0, 0], '+y': [0, 1, 0], '-y': [0, -1, 0], '+z': [0, 0, 1], '-z': [0, 0, -1],
}

function zoneStyle(project: EngineeringProject, zoneId: string, pipeId: string): BoxStyle {
  const rules = project.constraints.filter((rule) => rule.scope.pipe_ids.includes(pipeId) && rule.scope.target_ids.includes(zoneId))
  if (rules.some((rule) => rule.status !== 'approved')) return 'pending-zone'
  if (rules.some((rule) => rule.type === 'KEEP_OUT')) return 'keep-out'
  return 'zone'
}

function routeModel(project: EngineeringProject, route: RouteSolveReport): SceneRoute | null {
  if (route.points_m.length < 2) return null
  const pipe = project.pipes.find((item) => item.id === route.pipe_id)
  const invalid = new Set(route.validation?.violations.map((item) => item.segment_index) ?? [])
  const points = route.points_m.map(worldToScene)
  const segments: SceneSegment[] = []
  for (let index = 0; index < points.length - 1; index++) {
    const from = points[index]
    const to = points[index + 1]
    const delta: ScenePoint = [to[0] - from[0], to[1] - from[1], to[2] - from[2]]
    const length = Math.hypot(...delta)
    if (length === 0) continue
    segments.push({
      index, from, to, length, invalid: invalid.has(index),
      center: [(from[0] + to[0]) / 2, (from[1] + to[1]) / 2, (from[2] + to[2]) / 2],
      direction: [delta[0] / length, delta[1] / length, delta[2] / length],
    })
  }
  const radius = pipe ? pipe.outer_diameter_m / 2 + pipe.insulation_thickness_m : route.grid_resolution_m / 4
  return { pipeId: route.pipe_id, points, segments, radius }
}

/**
 * Builds everything the 3D viewer draws from the EngineeringProject JSON and a route report.
 * Meshes are derived from this model on every change and are never read back into the project.
 */
export function buildSceneModel(project: EngineeringProject, route: RouteSolveReport | null, pipeId: string): SceneModel {
  const boxes: SceneBox[] = [
    ...project.obstacles.map((item): SceneBox => ({
      selection: { kind: 'obstacle', id: item.id },
      style: item.kind === 'slab' ? 'slab' : 'obstacle',
      ...worldBoxToScene(item.shape),
    })),
    ...project.zones.map((item): SceneBox => ({
      selection: { kind: 'zone', id: item.id },
      style: zoneStyle(project, item.id, pipeId),
      ...worldBoxToScene(item.shape),
    })),
  ]
  const stub = Math.max(project.routing_config.grid_resolution_m, 0.2)
  const pipe = project.pipes.find((item) => item.id === pipeId)
  const ports = project.equipment.flatMap((equipment) => equipment.ports.map((port): ScenePort => {
    const axis = orientationVector[port.orientation]
    const p = port.position_m
    return {
      id: port.id,
      center: worldToScene(p),
      tip: worldToScene([p[0] + axis[0] * stub, p[1] + axis[1] * stub, p[2] + axis[2] * stub]),
      role: port.id === pipe?.from_port_id ? 'start' : port.id === pipe?.to_port_id ? 'end' : null,
    }
  }))
  const waypoints = (pipe?.waypoints ?? []).map((waypoint, index): SceneWaypoint => {
    const p = waypoint.position_m
    const half = stub * 2
    const along = waypoint.pass_axis ? { x: 0, y: 1, z: 2 }[waypoint.pass_axis] : null
    const shifted = (sign: number): Point3 => p.map((value, axis) => axis === along ? value + sign * half : value) as Point3
    return {
      id: waypoint.id,
      order: index + 1,
      center: worldToScene(p),
      axis: along === null ? null : [worldToScene(shifted(-1)), worldToScene(shifted(1))],
    }
  })
  return {
    bounds: worldBoxToScene(project.building.bounds_m),
    boxes,
    ports,
    waypoints,
    route: route && route.pipe_id === pipeId ? routeModel(project, route) : null,
  }
}

/** IDs a rule applies to, for highlighting its targets. */
export function ruleTargetIds(project: EngineeringProject, ruleId: string | null): Set<string> {
  const rule = ruleId ? project.constraints.find((item) => item.id === ruleId) : undefined
  return new Set(rule?.scope.target_ids ?? [])
}

export type CameraPreset = 'aerial' | 'plan'

/**
 * Camera placement for a preset, computed in world metres and mapped through worldToScene.
 * The plan view looks straight down with world +Y pointing up on screen (as in the 2D editor);
 * a tiny -Y offset keeps OrbitControls' azimuth defined.
 */
export function cameraFor(bounds: Aabb, preset: CameraPreset): { position: ScenePoint; target: ScenePoint } {
  const min = bounds.min_m
  const max = bounds.max_m
  const center: [number, number, number] = [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2]
  const span = Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2])
  const position: [number, number, number] = preset === 'plan'
    ? [center[0], center[1] - span * 1e-3, center[2] + span * 1.15]
    : [center[0] - span * 0.6, center[1] - span * 1.0, center[2] + span * 0.85]
  return { position: worldToScene(position), target: worldToScene(center) }
}
