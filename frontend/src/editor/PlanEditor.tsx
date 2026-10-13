import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import Konva from 'konva'
import { Stage, Layer, Rect, Line, Arrow, Circle, Text, RegularPolygon } from 'react-konva'
import { Popup } from '../ui/Popup'
import { useHostWindow } from '../ui/HostWindow'
import { ToolIcon } from '../ui/ToolIcon'
import type { EngineeringProject, Point3, RouteSolveReport } from '../api/client'
import { fitView, planToWorld, screenToWorld, snapMeters, worldBoxToPlan, worldToPlan, zoomAt, type PlanView } from './coordinates.ts'
import { addWaypoint, createEquipment, createPort, deleteEquipment, deleteObject, drawBox, EQUIPMENT_KINDS, floorsShowing, pickConnection, pipeConnectionPoints, portRole, selectionLabel, routeFloorCrossings, snapToCellCentre, updateWaypoint, moveBox, resizeBox, routeSegmentsOnFloor, updatePort, type EquipmentKind, type BoxKind, type Corner, type Selection } from './model.ts'
import { ObjectInspector } from './ObjectInspector'
import { DomainSettings } from './DomainPanel'
import { RouteSequence } from './RouteSequence'
import { RulesPanel } from './RulesPanel'
import { ROLE_COLORS } from './roles.ts'
import { RouteStatusNotice } from './RouteStatusNotice'
import { failedPortId } from './routeFeedback'
import './PlanEditor.css'

type Mode = 'select' | 'pan' | 'connect' | 'add-obstacle' | 'add-zone' | 'add-port' | 'add-waypoint' | 'add-equipment'

export type EditorAction = { kind: 'add-waypoint' | 'connect' | 'add-rule'; portId?: string; targetId?: string; nonce: number }

type Props = {
  project: EngineeringProject
  route: RouteSolveReport | null
  selectedPipeId: string
  selection: Selection | null
  onSelectionChange: (selection: Selection | null) => void
  /** Rule open in the rules panel; its targets are highlighted here and in 3D. */
  focusRuleId: string
  onFocusRule: (ruleId: string) => void
  busy: boolean
  canUndo: boolean
  canRedo: boolean
  onUndo: () => void
  onRedo: () => void
  onCommit: (project: EngineeringProject) => void
  onApproveRule: (project: EngineeringProject, ruleId: string, reviewer: string) => void
  onSelectPipe: (pipeId: string) => void
  onSolve: () => void
  solving: boolean
  action?: EditorAction | null
  companion?: boolean
}

type Draft = { kind: BoxKind; start: Point3; end: Point3 }

const HEIGHT = 540
const corners: Corner[] = ['nw', 'ne', 'sw', 'se']

export function PlanEditor({
  project, route, selectedPipeId, selection, onSelectionChange: setSelection, focusRuleId, onFocusRule, busy, canUndo, canRedo, onUndo, onRedo, onCommit, onSelectPipe, onApproveRule, onSolve, solving, action, companion = false,
}: Props) {
  const host = useHostWindow()
  const viewportRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<Konva.Stage>(null)
  const [width, setWidth] = useState(860)
  const [height, setHeight] = useState(HEIGHT)
  const [view, setView] = useState<PlanView>(() => fitView(project.building.bounds_m, 860, HEIGHT))
  const [mode, setMode] = useState<Mode>('select')
  const [connectionStart, setConnectionStart] = useState<string | null>(null)
  const [snapEnabled, setSnapEnabled] = useState(true)
  const [floorId, setFloorId] = useState(project.building.floors[0]?.id ?? '')
  const [equipmentId, setEquipmentId] = useState(project.equipment[0]?.id ?? '')
  const [equipmentKind, setEquipmentKind] = useState<EquipmentKind>('pump')
  const [hovered, setHovered] = useState<Point3 | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [editorError, setEditorError] = useState<string | null>(null)
  const [domainOpen, setDomainOpen] = useState(false)
  const [rulesOpen, setRulesOpen] = useState(false)
  const [followedRuleId, setFollowedRuleId] = useState(focusRuleId)
  if (followedRuleId !== focusRuleId) {
    setFollowedRuleId(focusRuleId)
    if (focusRuleId) setRulesOpen(true)
  }
  const [newRuleRequest, setNewRuleRequest] = useState<{ targetId: string; nonce: number } | null>(null)
  const [handledAction, setHandledAction] = useState<EditorAction | null>(null)
  if (action && action !== handledAction) {
    setHandledAction(action)
    setEditorError(null)
    if (action.kind === 'add-rule' && action.targetId) {
      setRulesOpen(true)
      setNewRuleRequest({ targetId: action.targetId, nonce: action.nonce })
    } else if (action.kind !== 'add-rule') {
      setMode(action.kind)
      setConnectionStart(action.portId ?? null)
    }
  }
  const focusTargets = new Set(project.constraints.find((rule) => rule.id === focusRuleId)?.scope.target_ids ?? [])
  const bounds = project.building.bounds_m
  const failedPort = failedPortId(project, route)
  if (connectionStart && !project.equipment.some((item) => item.ports.some((port) => port.id === connectionStart))) setConnectionStart(null)
  // A selection made in the 3D view may sit on another storey; show the first floor that draws it.
  const [followedSelection, setFollowedSelection] = useState(selection)
  if (followedSelection !== selection) {
    setFollowedSelection(selection)
    const showing = selection ? floorsShowing(project, selection) : []
    if (showing.length && !showing.includes(floorId)) setFloorId(showing[0])
  }
  const floor = project.building.floors.find((item) => item.id === floorId) ?? project.building.floors[0]
  const chosenEquipmentId = project.equipment.some((item) => item.id === equipmentId)
    ? equipmentId : project.equipment[0]?.id ?? ''
  const selectedOwner = selection?.kind === 'obstacle'
    ? project.equipment.find((item) => item.geometry_ref === selection.id)
    : selection?.kind === 'port' ? project.equipment.find((item) => item.ports.some((port) => port.id === selection.id)) : null
  const activeEquipmentId = selectedOwner?.id ?? chosenEquipmentId
  const spanX = bounds.max_m[0] - bounds.min_m[0]
  const spanY = bounds.max_m[1] - bounds.min_m[1]
  const snapStep = project.routing_config.grid_resolution_m

  useEffect(() => {
    if (!viewportRef.current) return
    let measuredWidth = 0, measuredHeight = 0
    const observer = new (host as Window & typeof globalThis).ResizeObserver((entries) => {
      if (entries[0].contentRect.width <= 0) return
      const nextWidth = Math.max(240, Math.floor(entries[0].contentRect.width))
      const nextHeight = companion ? Math.max(300, Math.floor(entries[0].contentRect.height)) : Math.max(300, Math.min(HEIGHT, Math.round(nextWidth * 0.66)))
      if (nextWidth === measuredWidth && nextHeight === measuredHeight) return
      measuredWidth = nextWidth
      measuredHeight = nextHeight
      setWidth(nextWidth)
      setHeight(nextHeight)
      setView(fitView(bounds, nextWidth, nextHeight))
    })
    observer.observe(viewportRef.current)
    return () => observer.disconnect()
  }, [bounds, companion, host])

  // Konva schedules batch draws in the main JS realm. Draw the portal on its own
  // window's frame too, so resizing/editing still paints when the main RAF pauses.
  useEffect(() => {
    if (host === window) return
    const frame = host.requestAnimationFrame(() => stageRef.current?.draw())
    return () => host.cancelAnimationFrame(frame)
  })
  useEffect(() => {
    if (host === window) return
    let pressed = false, frame = 0
    const down = () => { pressed = true }
    const up = () => { pressed = false }
    const draw = () => {
      if (pressed) stageRef.current?.draw()
      frame = host.requestAnimationFrame(draw)
    }
    host.document.addEventListener('pointerdown', down)
    host.document.addEventListener('pointerup', up)
    host.document.addEventListener('pointercancel', up)
    host.addEventListener('blur', up)
    frame = host.requestAnimationFrame(draw)
    return () => {
      host.cancelAnimationFrame(frame)
      host.document.removeEventListener('pointerdown', down)
      host.document.removeEventListener('pointerup', up)
      host.document.removeEventListener('pointercancel', up)
      host.removeEventListener('blur', up)
    }
  }, [host])

  const gridStep = useMemo(() => {
    let step = snapStep
    while (spanX / step > 130 || spanY / step > 130) step *= 2
    return step
  }, [snapStep, spanX, spanY])
  const gridX = useMemo(() => Array.from({ length: Math.floor(spanX / gridStep) + 1 }, (_, index) => index * gridStep), [spanX, gridStep])
  const gridY = useMemo(() => Array.from({ length: Math.floor(spanY / gridStep) + 1 }, (_, index) => index * gridStep), [spanY, gridStep])
  const routeSegments = route && floor ? routeSegmentsOnFloor(route.points_m, floor) : []
  const routeFloorIds = new Set(route ? project.building.floors.filter((item) => routeSegmentsOnFloor(route.points_m, item).length).map((item) => item.id) : [])
  const crossings = route && floor ? routeFloorCrossings(route.points_m, floor, project.building.floors) : []
  const invalidSegments = new Set(route?.validation?.violations.map((item) => item.segment_index) ?? [])
  const anyPendingRule = project.constraints.some((item) => item.scope.pipe_ids.includes(selectedPipeId) && item.status !== 'approved')

  function commit(next: EngineeringProject) {
    setEditorError(null)
    onCommit(next)
  }

  function onError(message: string) {
    setEditorError(message)
  }

  function tryCommit(change: () => EngineeringProject): boolean {
    try {
      commit(change())
      return true
    } catch (error) {
      onError(error instanceof Error ? error.message : '객체를 변경하지 못했습니다.')
      return false
    }
  }

  function deleteSelected() {
    if (!selection || busy) return
    const owner = selection.kind === 'obstacle' ? project.equipment.find((item) => item.geometry_ref === selection.id) : null
    if (tryCommit(() => owner ? deleteEquipment(project, owner.id) : deleteObject(project, selection))) setSelection(null)
  }

  function chooseMode(next: Mode) {
    setMode(next)
    setConnectionStart(null)
    setEditorError(null)
  }

  function selectPipe(id: string) {
    if (selectedPipeId !== id) onSelectPipe(id)
    setSelection({ kind: 'pipe', id })
  }

  function choosePort(id: string) {
    if (busy) return
    if (mode !== 'connect') { setSelection({ kind: 'port', id }); return }
    try {
      const picked = pickConnection(project, connectionStart, id)
      setEditorError(null)
      setConnectionStart(picked.startPortId)
      if (picked.pipeId) {
        commit(picked.project)
        onSelectPipe(picked.pipeId)
        setSelection({ kind: 'pipe', id: picked.pipeId })
        chooseMode('select')
      }
    } catch (error) { onError(error instanceof Error ? error.message : '연결점을 확인해 주세요.') }
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (!viewportRef.current?.checkVisibility() || viewportRef.current.closest('[inert]') || host.document.querySelector('dialog:modal')) return
      if (event.key === 'Escape') { chooseMode('select'); setDraft(null); return }
      if (event.key !== 'Delete' && event.key !== 'Backspace') return
      const target = event.target as HTMLElement | null
      if (target && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))) return
      if (!selection) return
      event.preventDefault()
      deleteSelected()
    }
    host.addEventListener('keydown', onKeyDown)
    return () => host.removeEventListener('keydown', onKeyDown)
  })

  function pointerWorld(): Point3 | null {
    const pointer = stageRef.current?.getPointerPosition()
    if (!pointer || !floor) return null
    return screenToWorld(pointer, (floor.z_min_m + floor.z_max_m) / 2, bounds, view)
  }

  function startDraft() {
    if (busy || (mode !== 'add-obstacle' && mode !== 'add-zone')) return
    const at = pointerWorld()
    if (at) setDraft({ kind: mode === 'add-obstacle' ? 'obstacle' : 'zone', start: at, end: at })
  }

  function finishDraft() {
    if (!draft || !floor) return
    const end = pointerWorld() ?? draft.end
    setDraft(null)
    try {
      const created = drawBox(project, draft.kind, draft.start, end, floor, snapEnabled ? snapStep : null)
      commit(created.project)
      setSelection(created.selection)
      setMode('select')
    } catch (error) { onError(error instanceof Error ? error.message : '객체를 만들지 못했습니다.') }
  }

  function zoom(factor: number, pointer = { x: width / 2, y: height / 2 }) {
    const fitted = fitView(bounds, width, height)
    setView((previous) => zoomAt(previous, pointer, factor, fitted.scale * 0.4, fitted.scale * 8))
  }

  function clickSurface() {
    if (busy || !floor) return
    if (mode === 'select') { setSelection(null); return }
    if (mode === 'add-waypoint') {
      const at = pointerWorld()
      if (!at) return
      try {
        const created = addWaypoint(project, selectedPipeId, at, floor, snapEnabled)
        commit(created.project)
        setSelection(created.selection)
      } catch (error) { onError(error instanceof Error ? error.message : '경유점을 만들지 못했습니다.') }
      return
    }
    if (mode !== 'add-port' && mode !== 'add-equipment') return
    const at = pointerWorld()
    if (!at) return
    try {
      const created = mode === 'add-equipment'
        ? createEquipment(project, equipmentKind, at, floor, snapEnabled ? snapStep : null)
        : createPort(project, activeEquipmentId, at, floor, snapEnabled ? snapStep : null)
      commit(created.project)
      setSelection(created.selection)
      if ('equipmentId' in created && typeof created.equipmentId === 'string') setEquipmentId(created.equipmentId)
      setMode('select')
    } catch (error) { onError(error instanceof Error ? error.message : '객체를 만들지 못했습니다.') }
  }

  function renderBox(kind: BoxKind, item: EngineeringProject['obstacles'][number] | EngineeringProject['zones'][number]) {
    if (!floor || item.shape.max_m[2] <= floor.z_min_m || item.shape.min_m[2] >= floor.z_max_m) return null
    const rect = worldBoxToPlan(item.shape, bounds)
    const selected = selection?.kind === kind && selection.id === item.id
    const rules = project.constraints.filter((rule) => rule.scope.pipe_ids.includes(selectedPipeId) && rule.scope.target_ids.includes(item.id))
    const restricted = kind === 'zone' && rules.some((rule) => rule.type === 'KEEP_OUT' && rule.status === 'approved')
    const pending = kind === 'zone' && rules.some((rule) => rule.status !== 'approved')
    // Slabs cover a whole storey; draw them as outlines so the plan beneath stays visible
    // and clicks inside reach the objects (with fill disabled Konva hit-tests only the stroke).
    const slab = kind === 'obstacle' && 'kind' in item && item.kind === 'slab'
    const owner = kind === 'obstacle' ? project.equipment.find((equipment) => equipment.geometry_ref === item.id) : null
    const fill = slab ? undefined : owner ? '#397f87' : kind === 'obstacle' ? '#7991a1' : restricted ? '#f4ad99a3' : '#f8d8929c'
    const focused = focusTargets.has(item.id)
    const stroke = selected ? '#0a8fb2' : focused ? '#c2337a' : slab ? '#8aa0ae' : kind === 'obstacle' ? '#52697b' : restricted ? '#c2614b' : '#c08b3f'
    const labelInside = rect.width * view.scale > 70 && rect.height * view.scale > 18
    const xMin = rect.x
    const xMax = rect.x + rect.width
    const yMin = rect.y
    const yMax = rect.y + rect.height
    return <Fragment key={`${kind}-${item.id}`}>
      <Rect
        x={rect.x} y={rect.y} width={rect.width} height={rect.height}
        fill={fill} stroke={stroke} strokeWidth={(selected || focused ? 3 : 1.6) / view.scale}
        dash={pending || slab ? [7 / view.scale, 4 / view.scale] : undefined}
        fillEnabled={!slab}
        listening={mode === 'select' || (mode === 'connect' && !!owner)}
        draggable={!busy && mode === 'select'}
        onClick={(event) => { event.cancelBubble = true; setSelection({ kind, id: item.id }) }}
        onTap={(event) => { event.cancelBubble = true; setSelection({ kind, id: item.id }) }}
        onDragEnd={(event) => {
          const node = event.target
          tryCommit(() => moveBox(project, kind, item.id, bounds.min_m[0] + node.x(), bounds.max_m[1] - node.y(), snapEnabled ? snapStep : null))
          node.position({ x: rect.x, y: rect.y })
        }}
      />
      <Text x={labelInside ? rect.x + 5 / view.scale : xMax + 3 / view.scale} y={labelInside ? rect.y + 5 / view.scale : yMin}
        text={selectionLabel(project, { kind, id: item.id })}
        fontSize={11 / view.scale} fill={slab ? '#6c8493' : kind === 'obstacle' && labelInside ? '#fff' : kind === 'obstacle' ? '#3b5566' : '#794b2e'} listening={false} />
      {selected && mode === 'select' && corners.map((corner) => {
        const x = corner.includes('w') ? xMin : xMax
        const y = corner.includes('n') ? yMin : yMax
        return <Circle key={corner} x={x} y={y} radius={6 / view.scale} fill="#fff" stroke="#078aad"
          strokeWidth={2 / view.scale} draggable={!busy}
          onDragEnd={(event) => {
            const node = event.target
            tryCommit(() => resizeBox(project, kind, item.id, corner, bounds.min_m[0] + node.x(), bounds.max_m[1] - node.y(), snapEnabled ? snapStep : null))
            node.position({ x, y })
          }}
        />
      })}
    </Fragment>
  }

  const sequencePipe = project.pipes.find((pipe) => pipe.id === selectedPipeId)
  const visibleWaypoints = floor && sequencePipe
    ? (sequencePipe.waypoints ?? []).map((waypoint, index) => ({ waypoint, index }))
      .filter(({ waypoint }) => waypoint.position_m[2] >= floor.z_min_m && waypoint.position_m[2] <= floor.z_max_m)
    : []
  const visiblePorts = floor ? project.equipment.flatMap((equipment) => equipment.ports.filter((port) => port.position_m[2] >= floor.z_min_m && port.position_m[2] <= floor.z_max_m)) : []

  return (
    <section className="plan-editor panel" aria-label="층별 2D 도면 편집기">
      <div className="plan-heading">
        <div><h2>배치도</h2><p>객체를 클릭해 수정하고, 연결점 두 개를 클릭해 배관을 만드세요.</p></div>
        <div className="plan-actions"><button type="button" className="button-secondary" disabled={!canUndo || busy} onClick={() => { onUndo(); setSelection(null) }}>↶ 실행 취소</button><button type="button" className="button-secondary" disabled={!canRedo || busy} onClick={() => { onRedo(); setSelection(null) }}>↷ 다시 실행</button></div>
      </div>
      <div className="plan-toolbar">
        <div className="tool-palette">
          <button type="button" className={mode === 'select' ? 'tool active' : 'tool'} aria-pressed={mode === 'select'} disabled={busy} onClick={() => chooseMode('select')}><ToolIcon kind="select" />선택</button>
          <div className="placement-tools" role="group" aria-label="객체 배치"><span className="tool-category">배치</span><div className="tool-group">
            {([['add-equipment', '기기 추가', 'equipment'], ['add-obstacle', '벽 추가', 'wall'], ['add-zone', '제약 구역 추가', 'zone']] as const).map(([value, label, icon]) => <button key={value} type="button" title={label} aria-pressed={mode === value} className={mode === value ? 'tool active' : 'tool'} disabled={busy} onClick={() => chooseMode(value)}><ToolIcon kind={icon} />{label}</button>)}
          </div></div>
          <div className="connection-tools" role="group" aria-label="배관 연결"><span className="tool-category">연결</span><button type="button" className={mode === 'connect' ? 'tool active' : 'tool'} aria-pressed={mode === 'connect'} disabled={busy || !project.equipment.length} onClick={() => chooseMode('connect')}><ToolIcon kind="connect" />배관 연결</button></div>
        </div>
        <div className="plan-run">
          <select aria-label="계산할 배관" disabled={busy || !project.pipes.length} value={selectedPipeId} onChange={(event) => selectPipe(event.target.value)}>
            {!project.pipes.length && <option value="">배관을 먼저 연결하세요</option>}
            {project.pipes.map((pipe) => <option key={pipe.id} value={pipe.id}>{selectionLabel(project, { kind: 'pipe', id: pipe.id })}</option>)}
          </select>
          <button type="button" className="button-primary" disabled={busy || !selectedPipeId} onClick={onSolve}>{solving ? '계산 중…' : '경로 계산'}</button>
        </div>
      </div>
      <div className="plan-settings-row">
        <div className="plan-settings">
          <label>층 <select value={floor?.id ?? ''} onChange={(event) => { setFloorId(event.target.value); setSelection(null) }}>{project.building.floors.map((item) => <option key={item.id} value={item.id}>{item.id} · z {item.z_min_m}–{item.z_max_m} m</option>)}</select></label>
          {mode === 'add-port' && <label>소유 기기 <select value={activeEquipmentId} onChange={(event) => { setEquipmentId(event.target.value); setSelection(null) }}>{project.equipment.map((item) => <option key={item.id} value={item.id}>{item.id}</option>)}</select></label>}
          {mode === 'add-equipment' && <label>추가할 기기 종류 <select aria-label="추가할 기기 종류" value={equipmentKind} onChange={(event) => setEquipmentKind(event.target.value as EquipmentKind)}>{Object.entries(EQUIPMENT_KINDS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>}
          <label className="snap-label"><input type="checkbox" checked={snapEnabled} onChange={(event) => setSnapEnabled(event.target.checked)} /> 스냅 {snapStep} m</label>
          <button type="button" className={mode === 'pan' ? 'tool active' : 'tool'} disabled={busy} onClick={() => chooseMode(mode === 'pan' ? 'select' : 'pan')}>화면 이동</button>
          <button type="button" className="tool" disabled={busy} onClick={() => { setEditorError(null); setDomainOpen(true) }}>건물·격자 설정</button>
        </div>
      </div>
      {domainOpen && <Popup title="건물·격자 설정" onClose={() => setDomainOpen(false)}>
        {editorError && <p className="plan-warning" role="alert">{editorError}</p>}
        <DomainSettings
          project={project} busy={busy} onCommit={(next) => { commit(next); setDomainOpen(false) }} onError={onError}
          open={true} onToggle={() => {}}
        />
      </Popup>}
      {(selection?.kind === 'waypoint' || mode === 'add-waypoint' || (selection?.kind === 'pipe' && !!sequencePipe?.waypoints?.length)) && <RouteSequence
        project={project} pipeId={selectedPipeId} selection={selection} busy={busy} adding={mode === 'add-waypoint'}
        onSelect={setSelection} onAdd={() => setMode(mode === 'add-waypoint' ? 'select' : 'add-waypoint')}
        onCommit={commit} onError={onError}
      />}
      {mode === 'connect' && <div className="connection-guide" role="status"><strong>{connectionStart ? '2. 도착 연결점을 클릭하세요' : '1. 시작 연결점을 클릭하세요'}</strong><span>점선은 연결 표시입니다. 실제 경로는 계산 후 표시됩니다.</span><button type="button" className="tool" onClick={() => chooseMode('select')}>연결 취소 · Esc</button></div>}
      <RouteStatusNotice project={project} route={route} busy={busy} onSelect={setSelection} />
      <div className="plan-body">
        <div className="plan-canvas-column">
          {anyPendingRule && <div className="plan-warning" role="status">미승인 규칙이 있습니다. 해당 배관은 승인 전 경로 실행이 거부됩니다.</div>}
          <div className={`canvas-viewport mode-${mode}`} ref={viewportRef} style={companion ? undefined : { height: height + 2 }}>
            {floor && <div className="floor-overlay" role="group" aria-label="표시 층">
              {project.building.floors.map((item) => (
                <button key={item.id} type="button" className={item.id === floor.id ? 'active' : ''} aria-pressed={item.id === floor.id}
                  title={`${item.id} · z ${item.z_min_m}–${item.z_max_m} m${routeFloorIds.has(item.id) ? ' · 경로 있음' : ''}`}
                  onClick={() => { setFloorId(item.id); setSelection(null) }}>
                  {item.id}{item.id === floor.id && <small> {item.z_min_m}–{item.z_max_m}m</small>}
                  {routeFloorIds.has(item.id) && <i className="floor-route-dot" aria-label="경로 있음" />}
                </button>
              ))}
            </div>}
            {editorError && <div className="plan-error" role="alert"><span><strong>반영되지 않음</strong> {editorError}</span><button type="button" aria-label="오류 닫기" onClick={() => setEditorError(null)}>×</button></div>}
            <Stage ref={stageRef} width={width} height={height} x={view.panX} y={view.panY} scaleX={view.scale} scaleY={view.scale}
              draggable={!busy && mode === 'pan'}
              onDragEnd={(event) => {
                if (event.target === stageRef.current) setView((previous) => ({ ...previous, panX: event.target.x(), panY: event.target.y() }))
              }}
              onWheel={(event) => {
                event.evt.preventDefault()
                const pointer = stageRef.current?.getPointerPosition()
                if (pointer) zoom(event.evt.deltaY < 0 ? 1.12 : 1 / 1.12, pointer)
              }}
              onMouseDown={startDraft}
              onMouseMove={() => {
                const at = pointerWorld()
                setHovered(at)
                if (at && draft) setDraft({ ...draft, end: at })
              }}
              onMouseUp={finishDraft}
              onMouseLeave={() => { setHovered(null); setDraft(null) }}
              onClick={(event) => { if (event.target === stageRef.current || event.target.name() === 'surface') clickSurface() }}
              onTap={(event) => { if (event.target === stageRef.current || event.target.name() === 'surface') clickSurface() }}
            >
              <Layer>
                <Rect name="surface" x={0} y={0} width={spanX} height={spanY} fill="#fbfdfe" stroke="#92a9b6" strokeWidth={2 / view.scale} />
                {gridX.map((x) => <Line key={`x-${x}`} points={[x, 0, x, spanY]} stroke="#e1eaf0" strokeWidth={1 / view.scale} listening={false} />)}
                {gridY.map((y) => <Line key={`y-${y}`} points={[0, y, spanX, y]} stroke="#e1eaf0" strokeWidth={1 / view.scale} listening={false} />)}
                {project.obstacles.filter((item) => item.kind === 'slab').map((item) => renderBox('obstacle', item))}
                {project.zones.map((item) => renderBox('zone', item))}
                {project.obstacles.filter((item) => item.kind !== 'slab').map((item) => renderBox('obstacle', item))}
                {project.pipes.flatMap((pipe) => {
                  if (route?.status === 'SUCCESS' && route.pipe_id === pipe.id && route.points_m.length > 1) return []
                  return routeSegmentsOnFloor(pipeConnectionPoints(project, pipe.id), floor).map((segment) => {
                    const start = worldToPlan(segment.from, bounds), end = worldToPlan(segment.to, bounds)
                    const selected = selection?.kind === 'pipe' && selection.id === pipe.id
                    const points = [start.x, start.y, end.x, end.y]
                    const color = selected ? '#087fad' : '#63889b'
                    const label = `${selectionLabel(project, { kind: 'pipe', id: pipe.id })} · 미계산`
                    const labelWidth = (label.length * 8 + 16) / view.scale
                    const midX = (start.x + end.x) / 2, midY = (start.y + end.y) / 2
                    return <Fragment key={`connection-${pipe.id}-${segment.index}`}>
                      <Line points={points} stroke={selected ? '#d1eef8' : '#fff'} strokeWidth={9 / view.scale} lineCap="round" listening={false} />
                      <Arrow points={points} dash={[4 / view.scale, 4 / view.scale]} stroke={color} fill={color} strokeWidth={2 / view.scale} lineCap="round" pointerLength={9 / view.scale} pointerWidth={8 / view.scale} hitStrokeWidth={16 / view.scale} listening={mode === 'select'} onClick={(event) => { event.cancelBubble = true; selectPipe(pipe.id) }} onTap={(event) => { event.cancelBubble = true; selectPipe(pipe.id) }} />
                      {selected && segment.index === 0 && <>
                        <Rect x={midX - labelWidth / 2} y={midY - 29 / view.scale} width={labelWidth} height={21 / view.scale} cornerRadius={6 / view.scale} fill="#f0f9fc" stroke="#b1d8e6" strokeWidth={1 / view.scale} listening={false} />
                        <Text x={midX - labelWidth / 2 + 8 / view.scale} y={midY - 24 / view.scale} text={label} fontSize={11 / view.scale} fill="#215b73" listening={false} />
                      </>}
                    </Fragment>
                  })
                })}
                {routeSegments.map((segment) => {
                  const start = worldToPlan(segment.from, bounds)
                  const end = worldToPlan(segment.to, bounds)
                  const invalid = invalidSegments.has(segment.index)
                  return <Line key={`route-${segment.index}`} points={[start.x, start.y, end.x, end.y]}
                    stroke={invalid ? '#df4047' : '#087fad'} strokeWidth={(invalid ? 5 : 3.5) / view.scale}
                    lineCap="round" lineJoin="round" hitStrokeWidth={14 / view.scale} listening={mode === 'select'} onClick={(event) => { event.cancelBubble = true; selectPipe(selectedPipeId) }} onTap={(event) => { event.cancelBubble = true; selectPipe(selectedPipeId) }} />
                })}
                {crossings.map((crossing) => {
                  const point = worldToPlan(crossing.at, bounds)
                  const label = `${crossing.direction === 'up' ? '↑' : '↓'} ${crossing.floorId}`
                  return <Fragment key={`cross-${point.x}-${point.y}-${crossing.direction}`}>
                    <Circle x={point.x} y={point.y} radius={7 / view.scale} fill="#087fad" stroke="#fff" strokeWidth={2 / view.scale} listening={false} />
                    <Rect x={point.x + 9 / view.scale} y={point.y - 19 / view.scale} width={(label.length * 7 + 10) / view.scale} height={17 / view.scale}
                      cornerRadius={8 / view.scale} fill="#087fad" listening={false} />
                    <Text x={point.x + 14 / view.scale} y={point.y - 16 / view.scale} text={label} fontSize={11 / view.scale} fontStyle="bold" fill="#fff" listening={false} />
                  </Fragment>
                })}
                {draft && (() => {
                  const a = worldToPlan(draft.start, bounds)
                  const b = worldToPlan(draft.end, bounds)
                  return <Rect x={Math.min(a.x, b.x)} y={Math.min(a.y, b.y)} width={Math.abs(b.x - a.x)} height={Math.abs(b.y - a.y)}
                    fill={draft.kind === 'obstacle' ? '#7991a166' : '#f8d89266'} stroke="#0a8fb2" strokeWidth={1.5 / view.scale}
                    dash={[6 / view.scale, 4 / view.scale]} listening={false} />
                })()}
                {visiblePorts.map((port) => {
                  const point = worldToPlan(port.position_m, bounds)
                  const selected = selection?.kind === 'port' && selection.id === port.id
                  const role = mode === 'connect' ? (connectionStart === port.id ? 'start' : null) : portRole(project, selectedPipeId, port.id)
                  const roleColor = role ? ROLE_COLORS[role] : null
                  return <Fragment key={port.id}>
                    {failedPort === port.id && <Circle x={point.x} y={point.y} radius={15 / view.scale} stroke="#df4047" strokeWidth={3 / view.scale} fill="#ffe5e566" listening={false} />}
                    {selected && roleColor && <Circle x={point.x} y={point.y} radius={13 / view.scale} stroke="#087fad" strokeWidth={2 / view.scale} listening={false} />}
                    <Circle x={point.x} y={point.y} radius={(roleColor ? 9 : selected ? 8 : 6) / view.scale}
                      fill={roleColor ?? '#fff'} stroke={selected ? '#087fad' : roleColor ? '#ffffff' : '#105c77'} strokeWidth={(roleColor ? 2 : 2.5) / view.scale}
                      listening={mode === 'select' || mode === 'connect'}
                      draggable={!busy && mode === 'select'}
                      onClick={(event) => { event.cancelBubble = true; choosePort(port.id) }}
                      onTap={(event) => { event.cancelBubble = true; choosePort(port.id) }}
                      onDragEnd={(event) => {
                        const node = event.target
                        const moved = planToWorld({ x: node.x(), y: node.y() }, port.position_m[2], bounds)
                        const origin = project.coordinate_frame.origin_m
                        const snapped: Point3 = [
                          snapEnabled ? snapMeters(moved[0], snapStep, origin[0]) : moved[0],
                          snapEnabled ? snapMeters(moved[1], snapStep, origin[1]) : moved[1],
                          moved[2],
                        ]
                        tryCommit(() => updatePort(project, port.id, snapped))
                        node.position(point)
                      }} />
                    {role && <Text x={point.x - 4 / view.scale} y={point.y - 5.5 / view.scale} text={role === 'start' ? 'S' : 'E'}
                      fontSize={11 / view.scale} fontStyle="bold" fill="#fff" listening={false} />}
                    {(selected || role || mode === 'connect') && <Text x={point.x + 11 / view.scale} y={point.y - 8 / view.scale} text={role ? role === 'start' ? '시작' : '도착' : selectionLabel(project, { kind: 'port', id: port.id })}
                      fontSize={11 / view.scale} fontStyle={role ? 'bold' : 'normal'} fill={roleColor ?? '#194f67'} listening={false} />}
                  </Fragment>
                })}
                {visibleWaypoints.map(({ waypoint, index }) => {
                  const point = worldToPlan(waypoint.position_m, bounds)
                  const selected = selection?.kind === 'waypoint' && selection.id === waypoint.id
                  const label = String(index + 1)
                  return <Fragment key={waypoint.id}>
                    <RegularPolygon x={point.x} y={point.y} sides={4} radius={(selected ? 13 : 11) / view.scale}
                      fill={ROLE_COLORS.waypoint} stroke={selected ? '#087fad' : '#fff'} strokeWidth={(selected ? 3 : 2) / view.scale}
                      listening={mode === 'select'}
                      draggable={!busy && mode === 'select'}
                      onClick={(event) => { event.cancelBubble = true; setSelection({ kind: 'waypoint', id: waypoint.id }) }}
                      onTap={(event) => { event.cancelBubble = true; setSelection({ kind: 'waypoint', id: waypoint.id }) }}
                      onDragEnd={(event) => {
                        const node = event.target
                        const moved = planToWorld({ x: node.x(), y: node.y() }, waypoint.position_m[2], bounds)
                        const next = snapEnabled ? snapToCellCentre(project, moved) : moved
                        tryCommit(() => updateWaypoint(project, waypoint.id, { position: [next[0], next[1], waypoint.position_m[2]] }))
                        node.position(point)
                      }} />
                    <Text x={point.x - (label.length * 3.3) / view.scale} y={point.y - 5.5 / view.scale} text={label}
                      fontSize={11 / view.scale} fontStyle="bold" fill="#fff" listening={false} />
                    <Text x={point.x + 14 / view.scale} y={point.y - 8 / view.scale}
                      text={`경유점 ${index + 1}${waypoint.pass_axis ? ` · ${waypoint.pass_axis.toUpperCase()}축 통과` : ''}`}
                      fontSize={11 / view.scale} fill="#9a5a06" listening={false} />
                  </Fragment>
                })}
                <Text x={0} y={spanY + 10 / view.scale} text={`X →  |  Y ↑  |  ${floor?.id ?? ''}`} fill="#526f7f" fontSize={11 / view.scale} listening={false} />
              </Layer>
            </Stage>
            <div className="canvas-controls"><button type="button" onClick={() => zoom(1.25)} aria-label="확대">+</button><button type="button" onClick={() => zoom(1 / 1.25)} aria-label="축소">−</button><button type="button" onClick={() => setView(fitView(bounds, width, height))} aria-label="화면 맞춤">□</button></div>
          </div>
          <div className="canvas-footer"><span>{mode === 'connect' ? '연결점을 차례로 클릭하세요 · Esc로 취소' : mode === 'pan' ? '드래그하여 화면 이동 · 휠 확대/축소' : mode === 'add-equipment' ? '도면을 클릭해 기기를 배치하세요.' : mode === 'add-port' ? '도면을 클릭해 선택 기기의 연결점을 추가하세요.' : mode === 'add-waypoint' ? '도면을 클릭해 경유점을 추가하세요 · 선택 또는 Esc로 종료' : mode.startsWith('add') ? '드래그해서 영역을 그리세요.' : '클릭해 선택 · 드래그로 이동 · 휠 확대/축소'}</span><strong>{hovered ? `X ${hovered[0].toFixed(2)} · Y ${hovered[1].toFixed(2)} m` : '세계좌표 m'}</strong></div>
          <div className="plan-legend"><span><i className="legend-wall" /> 벽/기기</span><span><i className="legend-zone" /> 제약 구역</span><span><i className="legend-port" /> 연결점</span><span>┄ 연결 표시 (계산 전)</span><span><i className="legend-route" /> 계산된 경로</span><span><i className="legend-invalid" /> 위반 구간</span></div>
        </div>
        <ObjectInspector
          key={`${selection?.kind}:${selection?.id}`}
          project={project} selection={selection} selectedPipeId={selectedPipeId} busy={busy}
          onCommit={commit} onError={onError} onSelect={(next) => { if (next.kind === 'pipe') selectPipe(next.id); else setSelection(next) }}
          onAddPort={(id) => { setEquipmentId(id); chooseMode('add-port') }}
          onAddWaypoint={() => chooseMode('add-waypoint')}
          onConnect={(id) => { chooseMode('connect'); if (id) setConnectionStart(id) }}
          onFocusRule={(id) => { onFocusRule(id); setRulesOpen(true) }}
          onAddRule={(targetId) => { setRulesOpen(true); setNewRuleRequest((request) => ({ targetId, nonce: (request?.nonce ?? 0) + 1 })) }}
        />
      </div>
      <details className="inspector-details rule-drawer" open={rulesOpen} onToggle={(event) => setRulesOpen(event.currentTarget.open)}><summary>제약 규칙 · 승인 관리 ({project.constraints.length})</summary><RulesPanel
        project={project} selectedPipeId={selectedPipeId} busy={busy}
        focusRuleId={focusRuleId} onFocusRule={onFocusRule} newRuleRequest={newRuleRequest}
        onCommit={commit}
        onApproveRule={onApproveRule}
      /></details>
    </section>
  )
}
