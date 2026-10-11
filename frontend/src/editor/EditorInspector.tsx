import { useState, type FormEvent } from 'react'
import type { EngineeringProject, Point3, Port, Waypoint } from '../api/client'
import {
  RULE_STATUS_TEXT, RULE_TYPE_TEXT, connectPort, describeRule, findWaypoint, portRole, reorderWaypoint, updateBox, updatePort,
  updateWaypoint, type Selection,
} from './model.ts'

type Props = {
  project: EngineeringProject
  selection: Selection | null
  selectedPipeId: string
  busy: boolean
  onCommit: (project: EngineeringProject) => void
  onError: (message: string) => void
  onDelete: () => void
  /** Opens a rule in the rules panel (and highlights its targets). */
  onFocusRule: (ruleId: string) => void
  /** Opens the new-rule form in the rules panel with this target. */
  onAddRule: (targetId: string) => void
}

type GeometryDraft = {
  minX: string; minY: string; minZ: string
  maxX: string; maxY: string; maxZ: string
  x: string; y: string; z: string
  orientation: Port['orientation']
  passAxis: NonNullable<Waypoint['pass_axis']> | ''
  note: string
}

const emptyGeometry: GeometryDraft = {
  minX: '', minY: '', minZ: '', maxX: '', maxY: '', maxZ: '',
  x: '', y: '', z: '', orientation: '+x', passAxis: '', note: '',
}

function draftFor(project: EngineeringProject, selection: Selection | null): GeometryDraft {
  if (!selection) return emptyGeometry
  if (selection.kind === 'waypoint') {
    const waypoint = findWaypoint(project, selection.id)?.waypoint
    if (!waypoint) return emptyGeometry
    const [x, y, z] = waypoint.position_m.map(String)
    return { ...emptyGeometry, x, y, z, passAxis: waypoint.pass_axis ?? '', note: waypoint.note ?? '' }
  }
  if (selection.kind === 'port') {
    const port = project.equipment.flatMap((item) => item.ports).find((item) => item.id === selection.id)
    if (!port) return emptyGeometry
    return { ...emptyGeometry, x: String(port.position_m[0]), y: String(port.position_m[1]), z: String(port.position_m[2]), orientation: port.orientation }
  }
  const item = (selection.kind === 'obstacle' ? project.obstacles : project.zones).find((entry) => entry.id === selection.id)
  if (!item) return emptyGeometry
  return {
    ...emptyGeometry,
    minX: String(item.shape.min_m[0]), minY: String(item.shape.min_m[1]), minZ: String(item.shape.min_m[2]),
    maxX: String(item.shape.max_m[0]), maxY: String(item.shape.max_m[1]), maxZ: String(item.shape.max_m[2]),
  }
}

function numeric(text: string): number {
  if (!text.trim() || !Number.isFinite(Number(text))) throw new Error('모든 좌표에 유한한 숫자를 입력해 주세요.')
  return Number(text)
}

export function EditorInspector({ project, selection, selectedPipeId, busy, onCommit, onError, onDelete, onFocusRule, onAddRule }: Props) {
  const [geometry, setGeometry] = useState<GeometryDraft>(() => draftFor(project, selection))

  function applyGeometry(event: FormEvent) {
    event.preventDefault()
    if (!selection) return
    try {
      if (selection.kind === 'waypoint') {
        const point: Point3 = [numeric(geometry.x), numeric(geometry.y), numeric(geometry.z)]
        onCommit(updateWaypoint(project, selection.id, { position: point, passAxis: geometry.passAxis || null, note: geometry.note }))
      } else if (selection.kind === 'port') {
        const point: Point3 = [numeric(geometry.x), numeric(geometry.y), numeric(geometry.z)]
        onCommit(updatePort(project, selection.id, point, geometry.orientation))
      } else {
        onCommit(updateBox(project, selection.kind, selection.id, {
          type: 'aabb',
          min_m: [numeric(geometry.minX), numeric(geometry.minY), numeric(geometry.minZ)],
          max_m: [numeric(geometry.maxX), numeric(geometry.maxY), numeric(geometry.maxZ)],
        }))
      }
    } catch (error) {
      onError(error instanceof Error ? error.message : '좌표를 변경하지 못했습니다.')
      setGeometry(draftFor(project, selection))
    }
  }

  const owner = selection?.kind === 'port'
    ? project.equipment.find((item) => item.ports.some((port) => port.id === selection.id))?.id
    : null
  const objectRules = selection ? project.constraints.filter((rule) => rule.scope.target_ids.includes(selection.id)) : []
  const waypointInfo = selection?.kind === 'waypoint' ? findWaypoint(project, selection.id) : null
  const role = selection?.kind === 'port' ? portRole(project, selectedPipeId, selection.id) : null
  const kindLabel = !selection ? '' : selection.kind === 'obstacle' ? '장애물' : selection.kind === 'zone' ? '제약 Zone'
    : selection.kind === 'waypoint' ? '필수 경유점' : 'Port'

  function reorder(delta: -1 | 1) {
    if (!waypointInfo) return
    try { onCommit(reorderWaypoint(project, waypointInfo.waypoint.id, delta)) }
    catch (error) { onError(error instanceof Error ? error.message : '순서를 바꾸지 못했습니다.') }
  }

  return (
    <aside className="editor-inspector" aria-label="도면 속성">
      <div className="inspector-heading"><span>속성</span><strong>{selection?.id ?? '객체 선택'}</strong></div>
      {!selection ? <p className="inspector-empty">도면에서 벽체, Zone, Port 또는 경유점을 선택하면 좌표와 속성을 변경할 수 있습니다. 도메인 크기·격자·배관 단면은 도면 위 설정에서 바꿉니다.</p> : (
        <form onSubmit={applyGeometry} className="inspector-form">
          <div className="inspector-meta"><span>종류</span><strong>{kindLabel}</strong></div>
          {owner && <div className="inspector-meta"><span>소유 장비</span><strong>{owner}</strong></div>}
          {role && <div className="inspector-meta"><span>{selectedPipeId}</span><strong className={`role-badge ${role}`}>{role === 'start' ? 'S · 시작점' : 'E · 끝점'}</strong></div>}
          {waypointInfo && <div className="inspector-meta"><span>{waypointInfo.pipe.id} 순서</span><strong className="role-badge waypoint">{waypointInfo.index + 1} / {waypointInfo.pipe.waypoints!.length}</strong></div>}
          {selection.kind === 'waypoint' ? (
            <>
              <div className="inspector-fields three">
                {(['x', 'y', 'z'] as const).map((axis) => <label key={axis}>{axis.toUpperCase()} (m)<input type="number" step="any" value={geometry[axis]} onChange={(event) => setGeometry({ ...geometry, [axis]: event.target.value })} /></label>)}
              </div>
              <label className="inspector-select">통과 방향<select value={geometry.passAxis} onChange={(event) => setGeometry({ ...geometry, passAxis: event.target.value as GeometryDraft['passAxis'] })}>
                <option value="">지정 안 함 · 이 점을 지나기만 함</option>
                <option value="x">X축으로 곧게 통과 (X 방향 벽 관통)</option>
                <option value="y">Y축으로 곧게 통과 (Y 방향 벽 관통)</option>
                <option value="z">Z축으로 곧게 통과 (바닥판 관통)</option>
              </select></label>
              <label className="inspector-select">메모 · 근거<input maxLength={500} placeholder="예: 토목도면 C-101 슬리브, 철근탐사 결과" value={geometry.note} onChange={(event) => setGeometry({ ...geometry, note: event.target.value })} /></label>
              <div className="inspector-actions">
                <button type="button" className="button-secondary" disabled={busy || !waypointInfo || waypointInfo.index === 0} onClick={() => reorder(-1)}>↑ 앞으로</button>
                <button type="button" className="button-secondary" disabled={busy || !waypointInfo || waypointInfo.index === waypointInfo.pipe.waypoints!.length - 1} onClick={() => reorder(1)}>↓ 뒤로</button>
              </div>
            </>
          ) : selection.kind === 'port' ? (
            <>
              <div className="inspector-fields three">
                {(['x', 'y', 'z'] as const).map((axis) => <label key={axis}>{axis.toUpperCase()} (m)<input type="number" step="any" value={geometry[axis]} onChange={(event) => setGeometry({ ...geometry, [axis]: event.target.value })} /></label>)}
              </div>
              <label className="inspector-select">포트 방향<select value={geometry.orientation} onChange={(event) => setGeometry({ ...geometry, orientation: event.target.value as Port['orientation'] })}>
                {['+x', '-x', '+y', '-y', '+z', '-z'].map((item) => <option key={item} value={item}>{item}</option>)}
              </select></label>
            </>
          ) : (
            <div className="inspector-fields three">
              {([
                ['minX', 'X 최소'], ['minY', 'Y 최소'], ['minZ', 'Z 최소'],
                ['maxX', 'X 최대'], ['maxY', 'Y 최대'], ['maxZ', 'Z 최대'],
              ] as const).map(([key, label]) => <label key={key}>{label} (m)<input type="number" step="any" value={geometry[key]} onChange={(event) => setGeometry({ ...geometry, [key]: event.target.value })} /></label>)}
            </div>
          )}
          <div className="inspector-actions">
            <button type="submit" className="button-secondary" disabled={busy}>{selection.kind === 'waypoint' ? '경유점 적용' : '좌표 적용'}</button>
            <button type="button" className="button-danger" disabled={busy} onClick={onDelete}>삭제</button>
          </div>
        </form>
      )}
      {selection?.kind === 'port' && selectedPipeId && (
        <div className="port-connect">
          <span>{selectedPipeId} 연결</span>
          <button type="button" className="button-secondary" onClick={() => {
            try { onCommit(connectPort(project, selectedPipeId, 'from', selection.id)) }
            catch (error) { onError(error instanceof Error ? error.message : '시작 Port를 지정하지 못했습니다.') }
          }}><span className="role-dot start" />시작 Port로 지정</button>
          <button type="button" className="button-secondary" onClick={() => {
            try { onCommit(connectPort(project, selectedPipeId, 'to', selection.id)) }
            catch (error) { onError(error instanceof Error ? error.message : '도착 Port를 지정하지 못했습니다.') }
          }}><span className="role-dot end" />도착 Port로 지정</button>
        </div>
      )}

      {selection && selection.kind !== 'waypoint' && <>
        <div className="inspector-divider" />
        <div className="inspector-heading"><span>Hard constraint</span><strong>이 객체가 대상인 규칙</strong></div>
        {objectRules.length ? <ul className="inspector-rules">
          {objectRules.map((rule) => <li key={rule.id}>
            <button type="button" onClick={() => onFocusRule(rule.id)} title="규칙 패널에서 열기">
              <span className={`type-badge ${rule.type}`}>{RULE_TYPE_TEXT[rule.type].name}</span>
              <span>{describeRule(rule)}</span>
              <small>{rule.id} · {RULE_STATUS_TEXT[rule.status]}</small>
            </button>
          </li>)}
        </ul> : <p className="inspector-empty">이 객체를 대상으로 하는 규칙이 없습니다.</p>}
        {(selection.kind === 'zone' || selection.kind === 'obstacle') && <button type="button" className="button-secondary" disabled={busy} onClick={() => onAddRule(selection.id)}>+ 이 객체에 규칙 추가</button>}
      </>}
    </aside>
  )
}
