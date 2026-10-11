import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import Konva from 'konva'
import { Stage, Layer, Rect, Line, Circle, Text } from 'react-konva'
import type { EngineeringProject, Point3, RouteSolveReport } from '../api/client'
import { fitView, planToWorld, screenToWorld, snapMeters, worldBoxToPlan, worldToPlan, zoomAt, type PlanView } from './coordinates.ts'
import { createBox, createPort, moveBox, resizeBox, routeSegmentsOnFloor, updatePort, type BoxKind, type Corner, type Selection } from './model.ts'
import { EditorInspector } from './EditorInspector'
import './PlanEditor.css'

type Mode = 'select' | 'pan' | 'add-obstacle' | 'add-zone' | 'add-port'

type Props = {
  project: EngineeringProject
  route: RouteSolveReport | null
  selectedPipeId: string
  busy: boolean
  canUndo: boolean
  canRedo: boolean
  onUndo: () => void
  onRedo: () => void
  onCommit: (project: EngineeringProject) => void
  onError: (message: string) => void
}

const HEIGHT = 540
const corners: Corner[] = ['nw', 'ne', 'sw', 'se']

export function PlanEditor({
  project, route, selectedPipeId, busy, canUndo, canRedo, onUndo, onRedo, onCommit, onError,
}: Props) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<Konva.Stage>(null)
  const [width, setWidth] = useState(860)
  const [view, setView] = useState<PlanView>(() => fitView(project.building.bounds_m, 860, HEIGHT))
  const [mode, setMode] = useState<Mode>('select')
  const [snapEnabled, setSnapEnabled] = useState(true)
  const [floorId, setFloorId] = useState(project.building.floors[0]?.id ?? '')
  const [equipmentId, setEquipmentId] = useState(project.equipment[0]?.id ?? '')
  const [selection, setSelection] = useState<Selection | null>(null)
  const [hovered, setHovered] = useState<Point3 | null>(null)
  const bounds = project.building.bounds_m
  const floor = project.building.floors.find((item) => item.id === floorId) ?? project.building.floors[0]
  const chosenEquipmentId = project.equipment.some((item) => item.id === equipmentId)
    ? equipmentId : project.equipment[0]?.id ?? ''
  const spanX = bounds.max_m[0] - bounds.min_m[0]
  const spanY = bounds.max_m[1] - bounds.min_m[1]
  const snapStep = project.routing_config.grid_resolution_m

  useEffect(() => {
    if (!viewportRef.current) return
    const observer = new ResizeObserver((entries) => {
      const nextWidth = Math.max(320, Math.floor(entries[0].contentRect.width))
      setWidth(nextWidth)
      setView(fitView(bounds, nextWidth, HEIGHT))
    })
    observer.observe(viewportRef.current)
    return () => observer.disconnect()
  }, [bounds])

  const gridStep = useMemo(() => {
    let step = snapStep
    while (spanX / step > 130 || spanY / step > 130) step *= 2
    return step
  }, [snapStep, spanX, spanY])
  const gridX = useMemo(() => Array.from({ length: Math.floor(spanX / gridStep) + 1 }, (_, index) => index * gridStep), [spanX, gridStep])
  const gridY = useMemo(() => Array.from({ length: Math.floor(spanY / gridStep) + 1 }, (_, index) => index * gridStep), [spanY, gridStep])
  const routeSegments = route && floor ? routeSegmentsOnFloor(route.points_m, floor) : []
  const invalidSegments = new Set(route?.validation?.violations.map((item) => item.segment_index) ?? [])
  const anyPendingRule = project.constraints.some((item) => item.scope.pipe_ids.includes(selectedPipeId) && item.status !== 'approved')

  function tryCommit(change: () => EngineeringProject): boolean {
    try {
      onCommit(change())
      return true
    } catch (error) {
      onError(error instanceof Error ? error.message : '객체를 변경하지 못했습니다.')
      return false
    }
  }

  function zoom(factor: number, pointer = { x: width / 2, y: HEIGHT / 2 }) {
    const fitted = fitView(bounds, width, HEIGHT)
    setView((previous) => zoomAt(previous, pointer, factor, fitted.scale * 0.4, fitted.scale * 8))
  }

  function clickSurface() {
    if (busy || !floor) return
    if (mode === 'select') { setSelection(null); return }
    if (mode === 'pan') return
    const pointer = stageRef.current?.getPointerPosition()
    if (!pointer) return
    const at = screenToWorld(pointer, (floor.z_min_m + floor.z_max_m) / 2, bounds, view)
    try {
      const created = mode === 'add-port'
        ? createPort(project, chosenEquipmentId, at, floor, snapEnabled ? snapStep : null)
        : createBox(project, mode === 'add-obstacle' ? 'obstacle' : 'zone', at, floor, snapEnabled ? snapStep : null)
      onCommit(created.project)
      setSelection(created.selection)
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
    const fill = kind === 'obstacle' ? '#7991a1' : restricted ? '#f4ad99a3' : '#f8d8929c'
    const stroke = selected ? '#0a8fb2' : kind === 'obstacle' ? '#52697b' : restricted ? '#c2614b' : '#c08b3f'
    const xMin = rect.x
    const xMax = rect.x + rect.width
    const yMin = rect.y
    const yMax = rect.y + rect.height
    return <Fragment key={`${kind}-${item.id}`}>
      <Rect
        x={rect.x} y={rect.y} width={rect.width} height={rect.height}
        fill={fill} stroke={stroke} strokeWidth={(selected ? 2.5 : 1.6) / view.scale}
        dash={pending ? [7 / view.scale, 4 / view.scale] : undefined}
        draggable={!busy && mode === 'select'}
        onClick={(event) => { event.cancelBubble = true; setSelection({ kind, id: item.id }) }}
        onTap={(event) => { event.cancelBubble = true; setSelection({ kind, id: item.id }) }}
        onDragEnd={(event) => {
          const node = event.target
          tryCommit(() => moveBox(project, kind, item.id, bounds.min_m[0] + node.x(), bounds.max_m[1] - node.y(), snapEnabled ? snapStep : null))
          node.position({ x: rect.x, y: rect.y })
        }}
      />
      <Text x={rect.x + 5 / view.scale} y={rect.y + 5 / view.scale} text={item.id}
        fontSize={11 / view.scale} fill={kind === 'obstacle' ? '#fff' : '#794b2e'} listening={false} />
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

  const visiblePorts = floor ? project.equipment.flatMap((equipment) => equipment.ports.filter((port) => port.position_m[2] >= floor.z_min_m && port.position_m[2] <= floor.z_max_m)) : []

  return (
    <section className="plan-editor panel" aria-label="층별 2D 도면 편집기">
      <div className="plan-heading">
        <div><p className="step">02 / PLAN EDITOR</p><h2>층별 배치도</h2><p>드래그로 이동하고 모서리 점으로 크기를 바꾸세요. 모든 좌표는 m 단위로 저장됩니다.</p></div>
        <div className="plan-actions"><button type="button" className="button-secondary" disabled={!canUndo || busy} onClick={() => { onUndo(); setSelection(null) }}>↶ 실행 취소</button><button type="button" className="button-secondary" disabled={!canRedo || busy} onClick={() => { onRedo(); setSelection(null) }}>↷ 다시 실행</button></div>
      </div>
      <div className="plan-toolbar">
        <div className="tool-group" role="group" aria-label="도면 도구">
          {([
            ['select', '선택'], ['pan', '이동'], ['add-obstacle', '벽 추가'],
            ['add-zone', 'Zone 추가'], ['add-port', 'Port 추가'],
          ] as const).map(([value, label]) => <button key={value} type="button" className={mode === value ? 'tool active' : 'tool'} disabled={busy} onClick={() => setMode(value)}>{label}</button>)}
        </div>
        <div className="plan-settings">
          <label>층 <select value={floor?.id ?? ''} onChange={(event) => { setFloorId(event.target.value); setSelection(null) }}>{project.building.floors.map((item) => <option key={item.id} value={item.id}>{item.id} · z {item.z_min_m}–{item.z_max_m} m</option>)}</select></label>
          {mode === 'add-port' && <label>장비 <select value={chosenEquipmentId} onChange={(event) => setEquipmentId(event.target.value)}>{project.equipment.map((item) => <option key={item.id} value={item.id}>{item.id}</option>)}</select></label>}
          <label className="snap-label"><input type="checkbox" checked={snapEnabled} onChange={(event) => setSnapEnabled(event.target.checked)} /> 스냅 {snapStep} m</label>
        </div>
      </div>
      <div className="plan-body">
        <div className="plan-canvas-column">
          {anyPendingRule && <div className="plan-warning" role="status">미승인 규칙이 있습니다. 해당 배관은 승인 전 경로 실행이 거부됩니다.</div>}
          <div className={`canvas-viewport mode-${mode}`} ref={viewportRef}>
            <Stage ref={stageRef} width={width} height={HEIGHT} x={view.panX} y={view.panY} scaleX={view.scale} scaleY={view.scale}
              draggable={!busy && mode === 'pan'}
              onDragEnd={(event) => {
                if (event.target === stageRef.current) setView((previous) => ({ ...previous, panX: event.target.x(), panY: event.target.y() }))
              }}
              onWheel={(event) => {
                event.evt.preventDefault()
                const pointer = stageRef.current?.getPointerPosition()
                if (pointer) zoom(event.evt.deltaY < 0 ? 1.12 : 1 / 1.12, pointer)
              }}
              onMouseMove={() => {
                const pointer = stageRef.current?.getPointerPosition()
                if (pointer && floor) setHovered(screenToWorld(pointer, (floor.z_min_m + floor.z_max_m) / 2, bounds, view))
              }}
              onMouseLeave={() => setHovered(null)}
              onClick={(event) => { if (event.target === stageRef.current || event.target.name() === 'surface') clickSurface() }}
              onTap={(event) => { if (event.target === stageRef.current || event.target.name() === 'surface') clickSurface() }}
            >
              <Layer>
                <Rect name="surface" x={0} y={0} width={spanX} height={spanY} fill="#fbfdfe" stroke="#92a9b6" strokeWidth={2 / view.scale} />
                {gridX.map((x) => <Line key={`x-${x}`} points={[x, 0, x, spanY]} stroke="#e1eaf0" strokeWidth={1 / view.scale} listening={false} />)}
                {gridY.map((y) => <Line key={`y-${y}`} points={[0, y, spanX, y]} stroke="#e1eaf0" strokeWidth={1 / view.scale} listening={false} />)}
                {project.zones.map((item) => renderBox('zone', item))}
                {project.obstacles.map((item) => renderBox('obstacle', item))}
                {routeSegments.map((segment) => {
                  const start = worldToPlan(segment.from, bounds)
                  const end = worldToPlan(segment.to, bounds)
                  const invalid = invalidSegments.has(segment.index)
                  return <Line key={`route-${segment.index}`} points={[start.x, start.y, end.x, end.y]}
                    stroke={invalid ? '#df4047' : '#087fad'} strokeWidth={(invalid ? 5 : 3.5) / view.scale}
                    lineCap="round" lineJoin="round" listening={false} />
                })}
                {visiblePorts.map((port) => {
                  const point = worldToPlan(port.position_m, bounds)
                  const selected = selection?.kind === 'port' && selection.id === port.id
                  return <Fragment key={port.id}>
                    <Circle x={point.x} y={point.y} radius={(selected ? 8 : 6) / view.scale}
                      fill="#fff" stroke={selected ? '#087fad' : '#105c77'} strokeWidth={2.5 / view.scale}
                      draggable={!busy && mode === 'select'}
                      onClick={(event) => { event.cancelBubble = true; setSelection({ kind: 'port', id: port.id }) }}
                      onTap={(event) => { event.cancelBubble = true; setSelection({ kind: 'port', id: port.id }) }}
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
                    <Text x={point.x + 9 / view.scale} y={point.y - 8 / view.scale} text={port.id}
                      fontSize={11 / view.scale} fill="#194f67" listening={false} />
                  </Fragment>
                })}
                <Text x={0} y={spanY + 10 / view.scale} text={`X →  |  Y ↑  |  ${floor?.id ?? ''}`} fill="#526f7f" fontSize={11 / view.scale} listening={false} />
              </Layer>
            </Stage>
            <div className="canvas-controls"><button type="button" onClick={() => zoom(1.25)} aria-label="확대">+</button><button type="button" onClick={() => zoom(1 / 1.25)} aria-label="축소">−</button><button type="button" onClick={() => setView(fitView(bounds, width, HEIGHT))} aria-label="화면 맞춤">□</button></div>
          </div>
          <div className="canvas-footer"><span>{mode === 'pan' ? '드래그하여 화면 이동 · 휠로 확대/축소' : mode.startsWith('add') ? '도면 내부를 클릭하면 객체가 생성됩니다.' : '객체 선택 · 드래그 이동 · 모서리 점으로 크기 변경'}</span><strong>{hovered ? `X ${hovered[0].toFixed(2)} · Y ${hovered[1].toFixed(2)} m` : '세계좌표 m'}</strong></div>
          <div className="plan-legend"><span><i className="legend-wall" /> 장애물</span><span><i className="legend-zone" /> Zone</span><span><i className="legend-port" /> Port</span><span><i className="legend-route" /> 경로</span><span><i className="legend-invalid" /> 위반 구간</span></div>
        </div>
        <EditorInspector
          key={`${selection?.kind ?? 'none'}:${selection?.id ?? ''}:${selectedPipeId}:${JSON.stringify(selection?.kind === 'port' ? visiblePorts.find((port) => port.id === selection.id) : selection?.kind === 'obstacle' ? project.obstacles.find((item) => item.id === selection.id) : project.zones.find((item) => item.id === selection?.id))}:${JSON.stringify(project.constraints)}`}
          project={project} selection={selection} selectedPipeId={selectedPipeId} onCommit={onCommit} onError={onError}
        />
      </div>
    </section>
  )
}
