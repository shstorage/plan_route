import type { Aabb, Constraint, EngineeringProject, Point3, Port } from '../api/client'
import { snapMeters } from './coordinates.ts'

export type BoxKind = 'obstacle' | 'zone'
export type Selection = { kind: BoxKind | 'port'; id: string }
export type Corner = 'nw' | 'ne' | 'sw' | 'se'
export type Floor = EngineeringProject['building']['floors'][number]

function checkBox(project: EngineeringProject, box: Aabb): void {
  const bounds = project.building.bounds_m
  for (let axis = 0; axis < 3; axis++) {
    if (!Number.isFinite(box.min_m[axis]) || !Number.isFinite(box.max_m[axis])) {
      throw new Error('모든 좌표는 유한한 숫자여야 합니다.')
    }
    if (box.max_m[axis] - box.min_m[axis] < 0.1 - 1e-9) {
      throw new Error('형상의 각 변은 최소 0.1 m여야 합니다.')
    }
    if (box.min_m[axis] < bounds.min_m[axis] - 1e-9 || box.max_m[axis] > bounds.max_m[axis] + 1e-9) {
      throw new Error('형상이 건물 경계 밖으로 나갈 수 없습니다.')
    }
  }
}

function checkPoint(project: EngineeringProject, point: Point3): void {
  const bounds = project.building.bounds_m
  for (let axis = 0; axis < 3; axis++) {
    if (!Number.isFinite(point[axis]) || point[axis] < bounds.min_m[axis] || point[axis] > bounds.max_m[axis]) {
      throw new Error('Port 좌표는 건물 내부의 유한한 값이어야 합니다.')
    }
  }
}

function boxFor(project: EngineeringProject, kind: BoxKind, id: string): Aabb {
  const box = (kind === 'obstacle' ? project.obstacles : project.zones).find((item) => item.id === id)?.shape
  if (!box) throw new Error(`객체 ${id}를 찾을 수 없습니다.`)
  return box
}

export function updateBox(project: EngineeringProject, kind: BoxKind, id: string, shape: Aabb): EngineeringProject {
  checkBox(project, shape)
  if (kind === 'obstacle') {
    if (!project.obstacles.some((item) => item.id === id)) throw new Error(`장애물 ${id}가 없습니다.`)
    return { ...project, obstacles: project.obstacles.map((item) => item.id === id ? { ...item, shape } : item) }
  }
  if (!project.zones.some((item) => item.id === id)) throw new Error(`Zone ${id}이 없습니다.`)
  return { ...project, zones: project.zones.map((item) => item.id === id ? { ...item, shape } : item) }
}

export function moveBox(
  project: EngineeringProject, kind: BoxKind, id: string,
  minX: number, maxY: number, snapStep: number | null,
): EngineeringProject {
  const old = boxFor(project, kind, id)
  const origin = project.coordinate_frame.origin_m
  const x = snapStep ? snapMeters(minX, snapStep, origin[0]) : minX
  const y = snapStep ? snapMeters(maxY, snapStep, origin[1]) : maxY
  const width = old.max_m[0] - old.min_m[0]
  const height = old.max_m[1] - old.min_m[1]
  return updateBox(project, kind, id, {
    type: 'aabb',
    min_m: [x, y - height, old.min_m[2]],
    max_m: [x + width, y, old.max_m[2]],
  })
}

export function resizeBox(
  project: EngineeringProject, kind: BoxKind, id: string,
  corner: Corner, worldX: number, worldY: number, snapStep: number | null,
): EngineeringProject {
  const old = boxFor(project, kind, id)
  const origin = project.coordinate_frame.origin_m
  const x = snapStep ? snapMeters(worldX, snapStep, origin[0]) : worldX
  const y = snapStep ? snapMeters(worldY, snapStep, origin[1]) : worldY
  const min: Point3 = [...old.min_m]
  const max: Point3 = [...old.max_m]
  if (corner.includes('w')) min[0] = x
  else max[0] = x
  if (corner.includes('n')) max[1] = y
  else min[1] = y
  return updateBox(project, kind, id, { type: 'aabb', min_m: min, max_m: max })
}

export function updatePort(project: EngineeringProject, id: string, position: Point3, orientation?: Port['orientation']): EngineeringProject {
  checkPoint(project, position)
  if (orientation && !['+x', '-x', '+y', '-y', '+z', '-z'].includes(orientation)) {
    throw new Error('Port 방향이 올바르지 않습니다.')
  }
  let found = false
  const equipment = project.equipment.map((item) => ({
    ...item,
    ports: item.ports.map((port) => {
      if (port.id !== id) return port
      found = true
      return { ...port, position_m: position, orientation: orientation ?? port.orientation }
    }),
  }))
  if (!found) throw new Error(`Port ${id}가 없습니다.`)
  return { ...project, equipment }
}

export function connectPort(
  project: EngineeringProject, pipeId: string, endpoint: 'from' | 'to', portId: string,
): EngineeringProject {
  if (!project.equipment.some((item) => item.ports.some((port) => port.id === portId))) {
    throw new Error(`Port ${portId}가 없습니다.`)
  }
  const pipe = project.pipes.find((item) => item.id === pipeId)
  if (!pipe) throw new Error(`배관 ${pipeId}가 없습니다.`)
  const opposite = endpoint === 'from' ? pipe.to_port_id : pipe.from_port_id
  if (opposite === portId) throw new Error('배관의 양 끝은 서로 다른 Port여야 합니다.')
  return {
    ...project,
    pipes: project.pipes.map((item) => item.id !== pipeId ? item : endpoint === 'from'
      ? { ...item, from_port_id: portId }
      : { ...item, to_port_id: portId }),
  }
}

function nextId(project: EngineeringProject, prefix: string): string {
  const ids = new Set<string>([
    project.project_id,
    ...project.building.floors.map((item) => item.id),
    ...project.obstacles.map((item) => item.id),
    ...project.zones.map((item) => item.id),
    ...project.equipment.flatMap((item) => [item.id, ...item.ports.map((port) => port.id)]),
    ...project.pipes.map((item) => item.id),
    ...project.constraints.map((item) => item.id),
  ])
  let number = 1
  while (ids.has(`${prefix}-${String(number).padStart(3, '0')}`)) number++
  return `${prefix}-${String(number).padStart(3, '0')}`
}

export function createBox(
  project: EngineeringProject, kind: BoxKind, at: Point3, floor: Floor, snapStep: number | null,
): { project: EngineeringProject; selection: Selection } {
  const size = Math.max(snapStep ?? project.routing_config.grid_resolution_m, 0.5)
  const origin = project.coordinate_frame.origin_m
  const x = snapStep ? snapMeters(at[0], snapStep, origin[0]) : at[0]
  const y = snapStep ? snapMeters(at[1], snapStep, origin[1]) : at[1]
  const shape: Aabb = {
    type: 'aabb',
    min_m: [x, y - size, floor.z_min_m],
    max_m: [x + size, y, floor.z_max_m],
  }
  checkBox(project, shape)
  if (kind === 'obstacle') {
    const id = nextId(project, 'WALL')
    return { project: { ...project, obstacles: [...project.obstacles, { id, kind: 'wall', shape }] }, selection: { kind, id } }
  }
  const id = nextId(project, 'ZONE')
  return { project: { ...project, zones: [...project.zones, { id, zone_type: 'restricted', shape }] }, selection: { kind, id } }
}

export function createPort(
  project: EngineeringProject, equipmentId: string, at: Point3, floor: Floor, snapStep: number | null,
): { project: EngineeringProject; selection: Selection } {
  const origin = project.coordinate_frame.origin_m
  const position: Point3 = [
    snapStep ? snapMeters(at[0], snapStep, origin[0]) : at[0],
    snapStep ? snapMeters(at[1], snapStep, origin[1]) : at[1],
    (floor.z_min_m + floor.z_max_m) / 2,
  ]
  checkPoint(project, position)
  if (!project.equipment.some((item) => item.id === equipmentId)) throw new Error('Port 소유 장비를 선택해 주세요.')
  const id = nextId(project, 'PORT')
  const port: Port = { id, position_m: position, orientation: '+x' }
  return {
    project: { ...project, equipment: project.equipment.map((item) => item.id === equipmentId ? { ...item, ports: [...item.ports, port] } : item) },
    selection: { kind: 'port', id },
  }
}

export type RuleEdit = {
  type: Constraint['type']
  status: Constraint['status']
  targetId: string
  distanceText: string
}

export function updateRule(project: EngineeringProject, ruleId: string, edit: RuleEdit): EngineeringProject {
  const rule = project.constraints.find((item) => item.id === ruleId)
  if (!rule) throw new Error(`규칙 ${ruleId}가 없습니다.`)
  if (rule.scope.target_ids.length !== 1) throw new Error('대상이 여러 개인 규칙은 JSON에서 수정해 주세요.')
  const targets = edit.type === 'KEEP_OUT' ? project.zones : [...project.zones, ...project.obstacles]
  if (!targets.some((item) => item.id === edit.targetId)) throw new Error('선택한 규칙 대상이 존재하지 않습니다.')
  if (!['draft', 'needs_review', 'approved', 'rejected'].includes(edit.status)) throw new Error('승인 상태가 올바르지 않습니다.')
  const distance = Number(edit.distanceText)
  if (edit.type === 'MIN_CLEARANCE' && (!edit.distanceText.trim() || !Number.isFinite(distance) || distance < 0)) {
    throw new Error('최소 이격 규칙에는 0 이상의 거리(m)를 입력해야 합니다.')
  }
  if (!rule.source.document_id || !rule.source.document_revision || !rule.source.clause_id || !rule.source.evidence_text) {
    throw new Error('규칙 출처와 근거가 필요합니다.')
  }
  const changed: Constraint = {
    ...rule,
    type: edit.type,
    status: edit.status,
    scope: { ...rule.scope, target_ids: [edit.targetId] },
    parameters: edit.type === 'KEEP_OUT' ? {} : {
      distance_m: distance,
      distance_basis: 'insulated_pipe_surface_to_target_surface',
    },
    approved_by: edit.status === 'approved' ? rule.approved_by : null,
    approved_at: edit.status === 'approved' ? rule.approved_at : null,
  }
  return { ...project, constraints: project.constraints.map((item) => item.id === ruleId ? changed : item) }
}

export type NewRule = {
  pipeId: string
  targetId: string
  type: Constraint['type']
  distanceText: string
  documentId: string
  revision: string
  clauseId: string
  evidence: string
}

export function createRule(project: EngineeringProject, input: NewRule): { project: EngineeringProject; id: string } {
  if (!project.pipes.some((pipe) => pipe.id === input.pipeId)) throw new Error('규칙 대상 배관이 없습니다.')
  const targets = input.type === 'KEEP_OUT' ? project.zones : [...project.zones, ...project.obstacles]
  if (!targets.some((item) => item.id === input.targetId)) throw new Error('규칙 대상 형상이 없습니다.')
  if (![input.documentId, input.revision, input.clauseId, input.evidence].every((text) => text.trim())) {
    throw new Error('규칙 출처·개정판·조항·근거 문구를 모두 입력해 주세요.')
  }
  const identifier = /^[A-Za-z][A-Za-z0-9_-]*$/
  if (!identifier.test(input.documentId.trim()) || !identifier.test(input.clauseId.trim())) {
    throw new Error('문서 ID와 조항 ID는 영문자로 시작하고 영문자·숫자·밑줄·하이픈만 허용합니다.')
  }
  const distance = Number(input.distanceText)
  if (input.type === 'MIN_CLEARANCE' && (!input.distanceText.trim() || !Number.isFinite(distance) || distance < 0)) {
    throw new Error('최소 이격거리(m)는 0 이상의 값이어야 합니다.')
  }
  const id = nextId(project, 'RULE')
  const rule: Constraint = {
    id,
    type: input.type,
    severity: 'hard',
    scope: { pipe_ids: [input.pipeId], target_ids: [input.targetId] },
    parameters: input.type === 'KEEP_OUT' ? {} : {
      distance_m: distance,
      distance_basis: 'insulated_pipe_surface_to_target_surface',
    },
    source: {
      source_type: 'synthetic_assumption',
      document_id: input.documentId.trim(),
      document_revision: input.revision.trim(),
      clause_id: input.clauseId.trim(),
      evidence_text: input.evidence.trim(),
    },
    status: 'draft',
  }
  return { project: { ...project, constraints: [...project.constraints, rule] }, id }
}

export function routeSegmentsOnFloor(points: Point3[], floor: Floor): Array<{ index: number; from: Point3; to: Point3 }> {
  const output: Array<{ index: number; from: Point3; to: Point3 }> = []
  for (let index = 0; index < points.length - 1; index++) {
    const from = points[index]
    const to = points[index + 1]
    const deltaZ = to[2] - from[2]
    let low = 0
    let high = 1
    if (deltaZ === 0) {
      if (from[2] < floor.z_min_m || from[2] > floor.z_max_m) continue
    } else {
      const t0 = (floor.z_min_m - from[2]) / deltaZ
      const t1 = (floor.z_max_m - from[2]) / deltaZ
      low = Math.max(0, Math.min(t0, t1))
      high = Math.min(1, Math.max(t0, t1))
      if (low > high) continue
    }
    const interpolate = (t: number): Point3 => [
      from[0] + (to[0] - from[0]) * t,
      from[1] + (to[1] - from[1]) * t,
      from[2] + deltaZ * t,
    ]
    output.push({ index, from: interpolate(low), to: interpolate(high) })
  }
  return output
}
