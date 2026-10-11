export type Point3 = [number, number, number]

export interface Aabb {
  type: 'aabb'
  min_m: Point3
  max_m: Point3
}

export interface Obstacle {
  id: string
  kind: string
  shape: Aabb
}

export interface Zone {
  id: string
  zone_type: string
  shape: Aabb
}

export interface Port {
  id: string
  position_m: Point3
  orientation: '+x' | '-x' | '+y' | '-y' | '+z' | '-z'
}

export interface Equipment {
  id: string
  kind: string
  geometry_ref?: string | null
  ports: Port[]
}

export interface Constraint {
  id: string
  type: 'KEEP_OUT' | 'MIN_CLEARANCE'
  severity: 'hard'
  scope: { pipe_ids: string[]; target_ids: string[] }
  parameters: {
    distance_m?: number | null
    distance_basis?: 'insulated_pipe_surface_to_target_surface' | null
  }
  source: {
    source_type: 'synthetic_assumption' | 'public_reference'
    document_id: string
    document_revision: string
    clause_id: string
    evidence_text: string
  }
  status: 'draft' | 'needs_review' | 'approved' | 'rejected'
  approved_by?: string | null
  approved_at?: string | null
}

export interface EngineeringProject {
  schema_version: string
  project_id: string
  study_type: string
  coordinate_frame: { name: string; unit: string; up_axis: string; origin_m: Point3 }
  building: {
    bounds_m: Aabb
    floors: Array<{ id: string; z_min_m: number; z_max_m: number }>
  }
  obstacles: Obstacle[]
  zones: Zone[]
  equipment: Equipment[]
  pipes: Pipe[]
  constraints: Constraint[]
  routing_config: { grid_resolution_m: number }
}

export interface Pipe {
  id: string
  from_port_id: string
  to_port_id: string
  outer_diameter_m: number
  insulation_thickness_m: number
  /** Optional in stored JSON; the backend treats a missing value as 0. */
  clearance_margin_m?: number
  train_id?: string | null
}

export interface HealthResponse {
  status: 'ok'
}

export interface ValidationIssue {
  location: Array<string | number>
  message: string
  type: string
}

export interface ProjectValidationResponse {
  valid: true
  project_id: string
  schema_version: string
}

export interface SavedProjectInfo {
  project_id: string
  schema_version: string
  revision: number
  updated_at: string
  document_hash: string
}

export interface RouteViolation {
  code: string
  segment_index: number
  object_id: string
  rule_id: string | null
  measured_distance_m: number
  required_distance_m: number
  message: string
}

export interface RouteSolveReport {
  status:
    | 'SUCCESS'
    | 'NO_PATH'
    | 'SEARCH_LIMIT_REACHED'
    | 'INVALID_INPUT'
    | 'UNAPPROVED_RULE'
    | 'RULE_CONFLICT'
    | 'INVALID_ROUTE'
    | 'RULES_NOT_COMPILED'
  project_id: string
  pipe_id: string
  algorithm: string
  grid_resolution_m: number
  points_m: Point3[]
  bend_count: number | null
  cost_breakdown: {
    path_length_m: number
    total_objective_cost: number
  } | null
  expanded_states: number
  runtime_ms: number
  applied_rule_ids: string[]
  scenario_hash: string
  result_id: string | null
  validation: {
    status: string
    checked_segments: number
    violations: RouteViolation[]
  } | null
  message: string
}

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL?.trim() || 'http://127.0.0.1:8000'
).replace(/\/+$/, '')

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export class ApiError extends Error {
  statusCode: number
  errorCode: string | null
  details: ValidationIssue[]

  constructor(statusCode: number, body: unknown) {
    const object = isRecord(body) ? body : {}
    const message = typeof object.message === 'string'
      ? object.message
      : `서버 응답 오류 (HTTP ${statusCode})`
    super(message)
    this.name = 'ApiError'
    this.statusCode = statusCode
    this.errorCode = typeof object.error_code === 'string' ? object.error_code : null
    this.details = Array.isArray(object.details)
      ? object.details.filter((entry): entry is ValidationIssue =>
          isRecord(entry) && Array.isArray(entry.location) && typeof entry.message === 'string' && typeof entry.type === 'string'
        )
      : []
  }
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  acceptSemanticStatus = false,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { Accept: 'application/json', ...init.headers },
    cache: 'no-store',
  })
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok && !(acceptSemanticStatus && isRecord(body) && typeof body.status === 'string')) {
    throw new ApiError(response.status, body)
  }
  if (body === null) throw new Error('서버가 JSON 응답을 반환하지 않았습니다.')
  return body as T
}

function jsonRequest(body: unknown, signal?: AbortSignal): RequestInit {
  return {
    method: 'POST',
    signal,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

function requireProject(value: unknown): EngineeringProject {
  if (!isRecord(value) || typeof value.project_id !== 'string' || !Array.isArray(value.pipes)) {
    throw new Error('서버의 프로젝트 응답 형식이 올바르지 않습니다.')
  }
  return value as unknown as EngineeringProject
}

export async function getHealth(signal: AbortSignal): Promise<HealthResponse> {
  const body = await requestJson<unknown>('/api/health', { signal })
  if (!isRecord(body) || body.status !== 'ok') {
    throw new Error('서버의 health 응답 형식이 올바르지 않습니다.')
  }
  return { status: 'ok' }
}

export type ExampleProject = 'starter' | 'demo'

export const exampleLabels: Record<ExampleProject, string> = {
  starter: '합성 플랜트 건물 60×40×12 m',
  demo: '소형 테스트 데모 12×10×4 m',
}

export async function getExampleProject(name: ExampleProject, signal?: AbortSignal): Promise<EngineeringProject> {
  return requireProject(await requestJson<unknown>(`/api/projects/${name}`, { signal }))
}

export async function getDemoProject(signal?: AbortSignal): Promise<EngineeringProject> {
  return getExampleProject('demo', signal)
}

export async function validateProject(project: unknown): Promise<ProjectValidationResponse> {
  return requestJson('/api/projects/validate', jsonRequest(project))
}

export async function saveProject(project: unknown): Promise<SavedProjectInfo> {
  return requestJson('/api/projects/save', jsonRequest(project))
}

export async function loadProject(projectId: string): Promise<{
  project: EngineeringProject
  revision: number
  updatedAt: string
}> {
  const response = await fetch(`${API_BASE_URL}/api/projects/${encodeURIComponent(projectId)}`, {
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  })
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, body)
  return {
    project: requireProject(body),
    revision: Number(response.headers.get('X-Project-Revision')),
    updatedAt: response.headers.get('X-Project-Updated-At') ?? '',
  }
}

export async function solveRoute(project: unknown, pipeId: string): Promise<RouteSolveReport> {
  return requestJson(
    '/api/routing/solve',
    jsonRequest({ project, pipe_id: pipeId }),
    true,
  )
}
