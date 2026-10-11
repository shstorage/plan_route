import type { Aabb, Constraint, EngineeringProject, Pipe, Point3, Port, Waypoint } from '../api/client'
import { snapMeters } from './coordinates.ts'

export type BoxKind = 'obstacle' | 'zone'
export type Selection = { kind: BoxKind | 'port' | 'waypoint'; id: string }
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
    ...project.pipes.flatMap((item) => [item.id, ...(item.waypoints ?? []).map((waypoint) => waypoint.id)]),
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

// Click (or a drag thinner than one snap step) falls back to createBox's default square.
export function drawBox(
  project: EngineeringProject, kind: BoxKind, start: Point3, end: Point3, floor: Floor, snapStep: number | null,
): { project: EngineeringProject; selection: Selection } {
  const origin = project.coordinate_frame.origin_m
  const snapX = (value: number) => snapStep ? snapMeters(value, snapStep, origin[0]) : value
  const snapY = (value: number) => snapStep ? snapMeters(value, snapStep, origin[1]) : value
  const minX = snapX(Math.min(start[0], end[0]))
  const maxX = snapX(Math.max(start[0], end[0]))
  const minY = snapY(Math.min(start[1], end[1]))
  const maxY = snapY(Math.max(start[1], end[1]))
  if (maxX - minX < 0.1 - 1e-9 || maxY - minY < 0.1 - 1e-9) {
    return createBox(project, kind, [start[0], start[1], start[2]], floor, snapStep)
  }
  const shape: Aabb = { type: 'aabb', min_m: [minX, minY, floor.z_min_m], max_m: [maxX, maxY, floor.z_max_m] }
  checkBox(project, shape)
  if (kind === 'obstacle') {
    const id = nextId(project, 'WALL')
    return { project: { ...project, obstacles: [...project.obstacles, { id, kind: 'wall', shape }] }, selection: { kind, id } }
  }
  const id = nextId(project, 'ZONE')
  return { project: { ...project, zones: [...project.zones, { id, zone_type: 'restricted', shape }] }, selection: { kind, id } }
}

// New ports reuse the height of an existing port on the floor, else 1 m above the slab (capped at mid-height).
export function defaultPortHeight(project: EngineeringProject, floor: Floor): number {
  const existing = project.equipment.flatMap((item) => item.ports)
    .find((port) => port.position_m[2] >= floor.z_min_m && port.position_m[2] <= floor.z_max_m)
  if (existing) return existing.position_m[2]
  return floor.z_min_m + Math.min(1, (floor.z_max_m - floor.z_min_m) / 2)
}

export function deleteObject(project: EngineeringProject, selection: Selection): EngineeringProject {
  if (selection.kind === 'waypoint') return removeWaypoint(project, selection.id)
  if (selection.kind === 'port') {
    const owner = project.equipment.find((item) => item.ports.some((port) => port.id === selection.id))
    if (!owner) throw new Error(`Port ${selection.id}가 없습니다.`)
    const pipes = project.pipes.filter((pipe) => pipe.from_port_id === selection.id || pipe.to_port_id === selection.id)
    if (pipes.length) throw new Error(`배관 ${pipes.map((pipe) => pipe.id).join(', ')}이(가) 연결된 Port는 삭제할 수 없습니다. 먼저 다른 Port로 연결을 바꿔 주세요.`)
    if (owner.ports.length === 1) throw new Error(`장비 ${owner.id}의 마지막 Port는 삭제할 수 없습니다.`)
    return {
      ...project,
      equipment: project.equipment.map((item) => item.id !== owner.id ? item : { ...item, ports: item.ports.filter((port) => port.id !== selection.id) }),
    }
  }
  boxFor(project, selection.kind, selection.id)
  const rules = project.constraints.filter((rule) => rule.scope.target_ids.includes(selection.id))
  if (rules.length) throw new Error(`규칙 ${rules.map((rule) => rule.id).join(', ')}이(가) 대상으로 쓰는 객체는 삭제할 수 없습니다. 먼저 규칙 대상을 바꿔 주세요.`)
  return selection.kind === 'obstacle'
    ? { ...project, obstacles: project.obstacles.filter((item) => item.id !== selection.id) }
    : { ...project, zones: project.zones.filter((item) => item.id !== selection.id) }
}

export type FloorEdit = { id: string; zMinText: string; zMaxText: string }
export type DomainEdit = {
  minText: [string, string, string]
  maxText: [string, string, string]
  floors: FloorEdit[]
  gridText: string
}

/** Above this many cells the browser asks before a slow solve; above MAX it refuses. */
export const CELL_WARNING = 400_000
export const CELL_LIMIT = 3_000_000

function parseMetres(text: string, label: string): number {
  const value = Number(text)
  if (!text.trim() || !Number.isFinite(value)) throw new Error(`${label}에 유한한 숫자(m)를 입력해 주세요.`)
  return value
}

/** Same rounding as the backend GridSpec: a clipped final cell still counts. */
export function gridCellCount(min: Point3, max: Point3, resolution: number): number {
  return [0, 1, 2].reduce((total, axis) => {
    const quotient = (max[axis] - min[axis]) / resolution
    const nearest = Math.round(quotient)
    return total * (nearest >= 1 && Math.abs(quotient - nearest) <= 1e-9 ? nearest : Math.ceil(quotient))
  }, 1)
}

export function updateDomain(project: EngineeringProject, edit: DomainEdit): EngineeringProject {
  const axes = ['X', 'Y', 'Z']
  const min = edit.minText.map((text, axis) => parseMetres(text, `도메인 ${axes[axis]} 최소`)) as Point3
  const max = edit.maxText.map((text, axis) => parseMetres(text, `도메인 ${axes[axis]} 최대`)) as Point3
  for (let axis = 0; axis < 3; axis++) {
    if (max[axis] - min[axis] < 0.1 - 1e-9) throw new Error(`도메인 ${axes[axis]} 크기는 최소 0.1 m여야 합니다.`)
  }
  const grid = parseMetres(edit.gridText, '격자 간격')
  if (grid < 0.05) throw new Error('격자 간격은 0.05 m 이상이어야 합니다.')
  const cells = gridCellCount(min, max, grid)
  if (cells > CELL_LIMIT) {
    throw new Error(`격자 칸이 ${cells.toLocaleString('ko-KR')}개로 너무 많습니다(한도 ${CELL_LIMIT.toLocaleString('ko-KR')}). 격자를 키우거나 도메인을 줄여 주세요.`)
  }
  if (project.building.floors.length !== edit.floors.length || edit.floors.some((floor, index) => floor.id !== project.building.floors[index].id)) {
    throw new Error('층 목록이 프로젝트와 일치하지 않습니다.')
  }
  const floors = edit.floors.map((floor, index) => {
    const zMin = parseMetres(floor.zMinText, `${floor.id} 바닥 z`)
    const zMax = parseMetres(floor.zMaxText, `${floor.id} 천장 z`)
    if (zMin >= zMax) throw new Error(`${floor.id}의 바닥 z는 천장 z보다 낮아야 합니다.`)
    if (zMin < min[2] - 1e-9 || zMax > max[2] + 1e-9) throw new Error(`${floor.id}가 도메인 Z 범위(${min[2]}–${max[2]} m) 밖에 있습니다.`)
    return { ...project.building.floors[index], z_min_m: zMin, z_max_m: zMax }
  })
  const inside = (point: Point3) => point.every((value, axis) => value >= min[axis] - 1e-9 && value <= max[axis] + 1e-9)
  const outside = [
    ...[...project.obstacles, ...project.zones].filter((item) => !inside(item.shape.min_m) || !inside(item.shape.max_m)).map((item) => item.id),
    ...project.equipment.flatMap((item) => item.ports).filter((port) => !inside(port.position_m)).map((port) => port.id),
  ]
  if (outside.length) throw new Error(`새 도메인 밖에 남는 객체가 있습니다: ${outside.join(', ')}. 먼저 옮기거나 삭제해 주세요.`)
  return {
    ...project,
    building: { ...project.building, bounds_m: { type: 'aabb', min_m: min, max_m: max }, floors },
    routing_config: { ...project.routing_config, grid_resolution_m: grid },
  }
}

/** UI shows pipe sizes in mm; the domain JSON always stores metres. */
export function metresToMillimetres(value: number): number {
  return Number((value * 1000).toFixed(6))
}

/** Returns a metre string, or the original text so updatePipe reports it as invalid. */
export function millimetresToMetres(text: string): string {
  const value = Number(text)
  return text.trim() && Number.isFinite(value) ? String(Number((value / 1000).toFixed(9))) : text
}

export type PipeEdit = { outerDiameterText: string; insulationText: string; marginText: string }

/** Diameter of the envelope the router keeps clear: OD + 2 x (insulation + margin). */
export function pipeEnvelopeDiameter(pipe: Pick<Pipe, 'outer_diameter_m' | 'insulation_thickness_m' | 'clearance_margin_m'>): number {
  return pipe.outer_diameter_m + 2 * (pipe.insulation_thickness_m + (pipe.clearance_margin_m ?? 0))
}

export function updatePipe(project: EngineeringProject, pipeId: string, edit: PipeEdit): EngineeringProject {
  if (!project.pipes.some((pipe) => pipe.id === pipeId)) throw new Error(`배관 ${pipeId}가 없습니다.`)
  const outer = parseMetres(edit.outerDiameterText, '외경')
  const insulation = parseMetres(edit.insulationText, '보온재 두께')
  const margin = parseMetres(edit.marginText, '추가 마진')
  if (outer <= 0) throw new Error('외경은 0보다 커야 합니다.')
  if (insulation < 0 || margin < 0) throw new Error('보온재 두께와 추가 마진은 0 이상이어야 합니다.')
  return {
    ...project,
    pipes: project.pipes.map((pipe) => pipe.id !== pipeId ? pipe : {
      ...pipe, outer_diameter_m: outer, insulation_thickness_m: insulation, clearance_margin_m: margin,
    }),
  }
}

export function createPort(
  project: EngineeringProject, equipmentId: string, at: Point3, floor: Floor, snapStep: number | null,
): { project: EngineeringProject; selection: Selection } {
  const origin = project.coordinate_frame.origin_m
  const position: Point3 = [
    snapStep ? snapMeters(at[0], snapStep, origin[0]) : at[0],
    snapStep ? snapMeters(at[1], snapStep, origin[1]) : at[1],
    defaultPortHeight(project, floor),
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
  pipeIds: string[]
  targetIds: string[]
  distanceText: string
}

export const RULE_TYPE_TEXT: Record<Constraint['type'], { name: string; meaning: string }> = {
  KEEP_OUT: {
    name: '진입 금지',
    meaning: '배관(보온재·마진 포함 외곽)이 대상 Zone 안에 들어가거나 경계에 닿으면 안 됩니다. Zone만 대상으로 할 수 있습니다.',
  },
  MIN_CLEARANCE: {
    name: '최소 이격',
    meaning: '배관 외곽 표면과 대상(Zone 또는 장애물) 표면 사이가 지정 거리 이상 떨어져야 합니다.',
  },
}

export const RULE_STATUS_TEXT: Record<Constraint['status'], string> = {
  draft: '초안', needs_review: '검토 대기', approved: '승인', rejected: '거부',
}

/** Allowed target IDs for a rule type: KEEP_OUT takes zones, MIN_CLEARANCE zones or obstacles. */
export function ruleTargetOptions(project: EngineeringProject, type: Constraint['type']): string[] {
  return (type === 'KEEP_OUT' ? project.zones : [...project.zones, ...project.obstacles]).map((item) => item.id)
}

/** One plain-language sentence for a rule, e.g. for lists and tooltips. */
export function describeRule(rule: Constraint): string {
  const pipes = rule.scope.pipe_ids.join(', ')
  const targets = rule.scope.target_ids.join(', ')
  return rule.type === 'KEEP_OUT'
    ? `${pipes} 배관은 ${targets} 안으로 들어갈 수 없습니다.`
    : `${pipes} 배관 외곽은 ${targets} 표면에서 ${rule.parameters.distance_m ?? '?'} m 이상 떨어져야 합니다.`
}

/** How a rule bears on one pipe: applied together with the others, blocking the run, or not related. */
export function ruleEffect(rule: Constraint, pipeId: string): 'applied' | 'blocking' | 'ignored' | 'other-pipe' {
  if (!rule.scope.pipe_ids.includes(pipeId)) return 'other-pipe'
  if (rule.status === 'approved') return 'applied'
  // The backend refuses to route a pipe while any of its rules is unapproved; rejected rules still count.
  return 'blocking'
}

function checkRuleScope(project: EngineeringProject, type: Constraint['type'], pipeIds: string[], targetIds: string[], distanceText: string): number | null {
  const pipes = new Set(project.pipes.map((pipe) => pipe.id))
  if (!pipeIds.length) throw new Error('규칙을 적용할 배관을 하나 이상 고르세요.')
  if (pipeIds.some((id) => !pipes.has(id))) throw new Error('존재하지 않는 배관이 포함되어 있습니다.')
  if (!targetIds.length) throw new Error('규칙 대상을 하나 이상 고르세요.')
  const allowed = new Set(ruleTargetOptions(project, type))
  const invalid = targetIds.filter((id) => !allowed.has(id))
  if (invalid.length) {
    throw new Error(type === 'KEEP_OUT'
      ? `진입 금지 규칙의 대상은 Zone이어야 합니다: ${invalid.join(', ')}`
      : `선택한 규칙 대상이 존재하지 않습니다: ${invalid.join(', ')}`)
  }
  if (new Set(pipeIds).size !== pipeIds.length || new Set(targetIds).size !== targetIds.length) {
    throw new Error('같은 배관이나 대상을 두 번 넣을 수 없습니다.')
  }
  if (type === 'KEEP_OUT') return null
  const distance = Number(distanceText)
  if (!distanceText.trim() || !Number.isFinite(distance) || distance < 0) {
    throw new Error('최소 이격 규칙에는 0 이상의 거리(m)를 입력해야 합니다.')
  }
  return distance
}

export function updateRule(project: EngineeringProject, ruleId: string, edit: RuleEdit): EngineeringProject {
  const rule = project.constraints.find((item) => item.id === ruleId)
  if (!rule) throw new Error(`규칙 ${ruleId}가 없습니다.`)
  if (!['draft', 'needs_review', 'approved', 'rejected'].includes(edit.status)) throw new Error('승인 상태가 올바르지 않습니다.')
  const distance = checkRuleScope(project, edit.type, edit.pipeIds, edit.targetIds, edit.distanceText)
  if (!rule.source.document_id || !rule.source.document_revision || !rule.source.clause_id || !rule.source.evidence_text) {
    throw new Error('규칙 출처와 근거가 필요합니다.')
  }
  const changed: Constraint = {
    ...rule,
    type: edit.type,
    status: edit.status,
    scope: { pipe_ids: [...edit.pipeIds], target_ids: [...edit.targetIds] },
    parameters: distance === null ? {} : {
      distance_m: distance,
      distance_basis: 'insulated_pipe_surface_to_target_surface',
    },
    approved_by: edit.status === 'approved' ? rule.approved_by : null,
    approved_at: edit.status === 'approved' ? rule.approved_at : null,
  }
  const definitionChanged = rule.type !== changed.type
    || JSON.stringify(rule.scope) !== JSON.stringify(changed.scope)
    || (rule.parameters.distance_m ?? null) !== (changed.parameters.distance_m ?? null)
    || (rule.parameters.distance_basis ?? null) !== (changed.parameters.distance_basis ?? null)
  if (definitionChanged) {
    changed.definition_revision = (rule.definition_revision ?? 1) + 1
  }
  if (definitionChanged || (edit.status === 'approved' && rule.status !== 'approved')) {
    changed.status = edit.status === 'rejected' ? 'rejected' : 'needs_review'
    changed.approved_by = null
    changed.approved_at = null
    changed.approved_content_sha256 = null
  }
  return { ...project, constraints: project.constraints.map((item) => item.id === ruleId ? changed : item) }
}

export function deleteRule(project: EngineeringProject, ruleId: string): EngineeringProject {
  if (!project.constraints.some((item) => item.id === ruleId)) throw new Error(`규칙 ${ruleId}가 없습니다.`)
  return { ...project, constraints: project.constraints.filter((item) => item.id !== ruleId) }
}

export type NewRule = {
  pipeIds: string[]
  targetIds: string[]
  type: Constraint['type']
  distanceText: string
  documentId: string
  revision: string
  clauseId: string
  evidence: string
}

export const SYNTHETIC_SOURCE_DOCUMENT = 'SYNTH-ASSUMPTION'

/**
 * Default provenance for a study assumption: a fixed synthetic document, the next free clause number
 * (A-1, A-2, ...) within it, and evidence text restating the rule. It is still provenance, not a code value.
 */
export function defaultRuleSource(project: EngineeringProject, rule: Pick<NewRule, 'type' | 'pipeIds' | 'targetIds' | 'distanceText'>) {
  const used = new Set(project.constraints
    .filter((item) => item.source.document_id === SYNTHETIC_SOURCE_DOCUMENT)
    .map((item) => item.source.clause_id))
  let number = 1
  while (used.has(`A-${number}`)) number++
  const pipes = rule.pipeIds.join(', ') || '(배관 미선택)'
  const targets = rule.targetIds.join(', ') || '(대상 미선택)'
  const statement = rule.type === 'KEEP_OUT'
    ? `${pipes} 배관은 ${targets} 안으로 들어가지 않는다.`
    : `${pipes} 배관 외곽은 ${targets} 표면에서 ${rule.distanceText.trim() || '?'} m 이상 떨어진다.`
  return {
    documentId: SYNTHETIC_SOURCE_DOCUMENT,
    revision: '1',
    clauseId: `A-${number}`,
    evidence: `연구용 가정(실제 법규·설계기준 값 아님): ${statement}`,
  }
}

/** Required inputs still empty in the new-rule form, in reading order. */
export function missingForNewRule(rule: NewRule): string[] {
  return [
    !rule.pipeIds.length && '적용 배관',
    !rule.targetIds.length && '대상',
    rule.type === 'MIN_CLEARANCE' && !rule.distanceText.trim() && '최소 거리',
    !rule.documentId.trim() && '문서 ID',
    !rule.revision.trim() && '개정판',
    !rule.clauseId.trim() && '조항 ID',
    !rule.evidence.trim() && '근거 문구',
  ].filter((item): item is string => Boolean(item))
}

export function createRule(project: EngineeringProject, input: NewRule): { project: EngineeringProject; id: string } {
  const distance = checkRuleScope(project, input.type, input.pipeIds, input.targetIds, input.distanceText)
  if (![input.documentId, input.revision, input.clauseId, input.evidence].every((text) => text.trim())) {
    throw new Error('규칙 출처·개정판·조항·근거 문구를 모두 입력해 주세요.')
  }
  const identifier = /^[A-Za-z][A-Za-z0-9_-]*$/
  if (!identifier.test(input.documentId.trim()) || !identifier.test(input.clauseId.trim())) {
    throw new Error('문서 ID와 조항 ID는 영문자로 시작하고 영문자·숫자·밑줄·하이픈만 허용합니다.')
  }
  const id = nextId(project, 'RULE')
  const rule: Constraint = {
    id,
    type: input.type,
    severity: 'hard',
    scope: { pipe_ids: [...input.pipeIds], target_ids: [...input.targetIds] },
    parameters: distance === null ? {} : {
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

/** Floors on which a selected object is drawn in the plan (z range intersects the storey). */
export function floorsShowing(project: EngineeringProject, selection: Selection): string[] {
  const floors = project.building.floors
  if (selection.kind === 'port' || selection.kind === 'waypoint') {
    const point = selection.kind === 'port'
      ? project.equipment.flatMap((item) => item.ports).find((item) => item.id === selection.id)?.position_m
      : findWaypoint(project, selection.id)?.waypoint.position_m
    if (!point) return []
    const z = point[2]
    return floors.filter((floor) => z >= floor.z_min_m && z <= floor.z_max_m).map((floor) => floor.id)
  }
  const shape = (selection.kind === 'obstacle' ? project.obstacles : project.zones).find((item) => item.id === selection.id)?.shape
  if (!shape) return []
  return floors.filter((floor) => shape.max_m[2] > floor.z_min_m && shape.min_m[2] < floor.z_max_m).map((floor) => floor.id)
}

/** Role of a port for one pipe: where the route starts or ends. */
export function portRole(project: EngineeringProject, pipeId: string, portId: string): 'start' | 'end' | null {
  const pipe = project.pipes.find((item) => item.id === pipeId)
  if (!pipe) return null
  return pipe.from_port_id === portId ? 'start' : pipe.to_port_id === portId ? 'end' : null
}

export function findWaypoint(project: EngineeringProject, id: string): { pipe: Pipe; waypoint: Waypoint; index: number } | null {
  for (const pipe of project.pipes) {
    const index = (pipe.waypoints ?? []).findIndex((item) => item.id === id)
    if (index >= 0) return { pipe, waypoint: pipe.waypoints![index], index }
  }
  return null
}

function withWaypoints(project: EngineeringProject, pipeId: string, waypoints: Waypoint[]): EngineeringProject {
  return { ...project, pipes: project.pipes.map((pipe) => pipe.id === pipeId ? { ...pipe, waypoints } : pipe) }
}

/**
 * Snap to a routing cell centre. The backend grid starts at building.bounds_m.min_m, so centres sit at
 * min + (i + 0.5) x resolution; a waypoint on a centre is matched exactly by the search.
 */
export function snapToCellCentre(project: EngineeringProject, point: Point3): Point3 {
  const step = project.routing_config.grid_resolution_m
  const bounds = project.building.bounds_m
  return point.map((value, axis) => {
    const low = bounds.min_m[axis] + step / 2
    const cells = Math.max(1, Math.ceil((bounds.max_m[axis] - bounds.min_m[axis]) / step - 1e-9))
    const snapped = snapMeters(value, step, low)
    return Math.min(Math.max(snapped, low), Number((low + (cells - 1) * step).toFixed(9)))
  }) as Point3
}

/** Adds a waypoint at the end of the pipe's sequence (just before the end port). */
export function addWaypoint(
  project: EngineeringProject, pipeId: string, at: Point3, floor: Floor, snap: boolean,
): { project: EngineeringProject; selection: Selection } {
  const pipe = project.pipes.find((item) => item.id === pipeId)
  if (!pipe) throw new Error('경유점을 추가할 배관을 먼저 선택해 주세요.')
  const existing = pipe.waypoints ?? []
  const onFloor = [...existing].reverse().find((item) => item.position_m[2] >= floor.z_min_m && item.position_m[2] <= floor.z_max_m)
  const raw: Point3 = [at[0], at[1], onFloor ? onFloor.position_m[2] : defaultPortHeight(project, floor)]
  const position = snap ? snapToCellCentre(project, raw) : raw
  checkPoint(project, position)
  const id = nextId(project, 'WP')
  return {
    project: withWaypoints(project, pipeId, [...existing, { id, position_m: position }]),
    selection: { kind: 'waypoint', id },
  }
}

export type WaypointEdit = { position?: Point3; passAxis?: Waypoint['pass_axis']; note?: string }

export function updateWaypoint(project: EngineeringProject, id: string, edit: WaypointEdit): EngineeringProject {
  const found = findWaypoint(project, id)
  if (!found) throw new Error(`경유점 ${id}가 없습니다.`)
  const next: Waypoint = { ...found.waypoint }
  if (edit.position) {
    checkPoint(project, edit.position)
    next.position_m = edit.position
  }
  if (edit.passAxis !== undefined) {
    if (edit.passAxis) next.pass_axis = edit.passAxis
    else delete next.pass_axis
  }
  if (edit.note !== undefined) {
    const note = edit.note.trim()
    if (note.length > 500) throw new Error('메모는 500자 이하로 입력해 주세요.')
    if (note) next.note = note
    else delete next.note
  }
  const waypoints = [...found.pipe.waypoints!]
  waypoints[found.index] = next
  return withWaypoints(project, found.pipe.id, waypoints)
}

/** Moves a waypoint one place earlier (-1) or later (+1) in its pipe's sequence. */
export function reorderWaypoint(project: EngineeringProject, id: string, delta: -1 | 1): EngineeringProject {
  const found = findWaypoint(project, id)
  if (!found) throw new Error(`경유점 ${id}가 없습니다.`)
  const target = found.index + delta
  const waypoints = [...found.pipe.waypoints!]
  if (target < 0 || target >= waypoints.length) return project
  ;[waypoints[found.index], waypoints[target]] = [waypoints[target], waypoints[found.index]]
  return withWaypoints(project, found.pipe.id, waypoints)
}

export function removeWaypoint(project: EngineeringProject, id: string): EngineeringProject {
  const found = findWaypoint(project, id)
  if (!found) throw new Error(`경유점 ${id}가 없습니다.`)
  const waypoints = found.pipe.waypoints!.filter((item) => item.id !== id)
  if (waypoints.length) return withWaypoints(project, found.pipe.id, waypoints)
  // Drop the empty list so a pipe without waypoints serialises exactly as before.
  return {
    ...project,
    pipes: project.pipes.map((pipe) => {
      if (pipe.id !== found.pipe.id) return pipe
      const rest = { ...pipe }
      delete rest.waypoints
      return rest
    }),
  }
}

export type FloorCrossing = { at: Point3; direction: 'up' | 'down'; floorId: string }

/**
 * Where the route leaves this floor's z range through its ceiling or floor plane, and the adjacent storey it
 * continues into. Used to mark storey transitions on a single-floor plan.
 */
export function routeFloorCrossings(points: Point3[], floor: Floor, floors: Floor[]): FloorCrossing[] {
  const output: FloorCrossing[] = []
  const seen = new Set<string>()
  for (let index = 0; index < points.length - 1; index++) {
    const from = points[index]
    const to = points[index + 1]
    const low = Math.min(from[2], to[2])
    const high = Math.max(from[2], to[2])
    if (high === low) continue
    for (const [plane, direction] of [[floor.z_max_m, 'up'], [floor.z_min_m, 'down']] as const) {
      const leaves = direction === 'up' ? high > plane && low < plane + 1e-9 : low < plane && high > plane - 1e-9
      if (!leaves || low > floor.z_max_m || high < floor.z_min_m) continue
      const t = (plane - from[2]) / (to[2] - from[2])
      const at: Point3 = [from[0] + (to[0] - from[0]) * t, from[1] + (to[1] - from[1]) * t, plane]
      const beyond = direction === 'up' ? plane + 1e-6 : plane - 1e-6
      const next = floors.find((item) => item.id !== floor.id && beyond >= item.z_min_m && beyond <= item.z_max_m)
      const key = `${at[0].toFixed(6)}:${at[1].toFixed(6)}:${direction}`
      if (seen.has(key)) continue
      seen.add(key)
      output.push({ at, direction, floorId: next?.id ?? (direction === 'up' ? '위층' : '아래층') })
    }
  }
  return output
}
