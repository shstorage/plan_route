import { memo, useEffect, useMemo, useState } from 'react'
import { Canvas, useThree, type ThreeEvent } from '@react-three/fiber'
import { Edges, Line, OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import type { Aabb, EngineeringProject, RouteSolveReport } from '../api/client'
import { pipeConnectionPoints, selectionLabel, type Selection } from '../editor/model.ts'
import { ROLE_COLORS } from '../editor/roles.ts'
import { TextLabel } from './TextLabel'
import { worldToScene, type ScenePoint } from './axes.ts'
import { buildSceneModel, cameraFor, ruleTargetIds, type BoxStyle, type CameraPreset, type SceneBox, type SceneSegment } from './scene.ts'
import './Viewer3D.css'
import { RouteStatusNotice } from '../editor/RouteStatusNotice'

type Props = {
  project: EngineeringProject
  route: RouteSolveReport | null
  selectedPipeId: string
  selection: Selection | null
  onSelect: (selection: Selection) => void
  /** Shared with the 2D rules panel. */
  focusRuleId: string
  onFocusRule: (ruleId: string) => void
  busy: boolean
  solving: boolean
  onSelectPipe: (pipeId: string) => void
  onSolve: () => void
}

type CameraRequest = { preset: CameraPreset; nonce: number }

const unitBox = new THREE.BoxGeometry(1, 1, 1)
const unitCylinder = new THREE.CylinderGeometry(1, 1, 1, 20)
const unitSphere = new THREE.SphereGeometry(1, 18, 12)
const unitOctahedron = new THREE.OctahedronGeometry(1)
const yAxis = new THREE.Vector3(0, 1, 0)
const noRaycast = () => null

const boxLook: Record<BoxStyle, { color: string; opacity: number; edge: string }> = {
  obstacle: { color: '#7991a1', opacity: 1, edge: '#52697b' },
  slab: { color: '#a9bac5', opacity: 0.12, edge: '#8aa0ae' },
  'keep-out': { color: '#e8826b', opacity: 0.32, edge: '#c2614b' },
  zone: { color: '#f2c46d', opacity: 0.28, edge: '#c08b3f' },
  'pending-zone': { color: '#f2c46d', opacity: 0.16, edge: '#b98a3f' },
}

const SELECTED = '#0a8fb2'
const RULE_TARGET = '#c2337a'

function selectionKey(selection: Selection | null): string {
  return selection ? `${selection.kind}:${selection.id}` : ''
}

const BoxMesh = memo(function BoxMesh({ box, selected, ruleTarget, onSelect }: {
  box: SceneBox
  selected: boolean
  ruleTarget: boolean
  onSelect: (selection: Selection) => void
}) {
  const look = boxLook[box.style]
  const transparent = look.opacity < 1
  const slab = box.style === 'slab'
  const edge = selected ? SELECTED : ruleTarget ? RULE_TARGET : look.edge
  return (
    <mesh
      geometry={unitBox}
      position={box.center}
      scale={box.size}
      // Slabs span a whole storey; letting them catch clicks would hide everything beneath.
      raycast={slab ? noRaycast : undefined}
      onClick={(event: ThreeEvent<MouseEvent>) => { event.stopPropagation(); onSelect(box.selection) }}
      onPointerOver={(event: ThreeEvent<PointerEvent>) => { event.stopPropagation(); document.body.style.cursor = 'pointer' }}
      onPointerOut={() => { document.body.style.cursor = '' }}
    >
      <meshStandardMaterial
        color={selected ? '#7cc8dc' : look.color}
        transparent={transparent}
        opacity={selected && transparent ? Math.min(0.55, look.opacity + 0.25) : look.opacity}
        depthWrite={!transparent}
      />
      <Edges color={edge} lineWidth={selected || ruleTarget ? 2.5 : 1} />
    </mesh>
  )
})

function TubeSegment({ segment, radius }: { segment: SceneSegment; radius: number }) {
  const quaternion = useMemo(
    () => new THREE.Quaternion().setFromUnitVectors(yAxis, new THREE.Vector3(...segment.direction)),
    [segment.direction],
  )
  return (
    <mesh geometry={unitCylinder} position={segment.center} quaternion={quaternion} scale={[radius, segment.length, radius]} raycast={noRaycast}>
      <meshStandardMaterial color={segment.invalid ? '#df4047' : '#1590bd'} transparent opacity={0.85} />
    </mesh>
  )
}

/** Floor grid over the building footprint at z = bounds min, spaced like the 2D editor grid. */
function FloorGrid({ bounds, step }: { bounds: Aabb; step: number }) {
  const geometry = useMemo(() => {
    const [x0, y0, z] = bounds.min_m
    const [x1, y1] = bounds.max_m
    const points: ScenePoint[] = []
    for (let x = x0; x <= x1 + 1e-9; x += step) points.push(worldToScene([x, y0, z]), worldToScene([x, y1, z]))
    for (let y = y0; y <= y1 + 1e-9; y += step) points.push(worldToScene([x0, y, z]), worldToScene([x1, y, z]))
    return new THREE.BufferGeometry().setFromPoints(points.map((point) => new THREE.Vector3(...point)))
  }, [bounds, step])
  useEffect(() => () => geometry.dispose(), [geometry])
  return <lineSegments geometry={geometry} raycast={noRaycast}>
    <lineBasicMaterial color="#cbd9e1" />
  </lineSegments>
}

function WorldAxes({ bounds }: { bounds: Aabb }) {
  const origin = bounds.min_m
  const length = Math.max(1, Math.min(bounds.max_m[0] - origin[0], bounds.max_m[1] - origin[1]) * 0.18)
  const axes: Array<{ label: string; color: string; end: ScenePoint }> = [
    { label: 'X', color: '#d6453d', end: worldToScene([origin[0] + length, origin[1], origin[2]]) },
    { label: 'Y', color: '#2f9e56', end: worldToScene([origin[0], origin[1] + length, origin[2]]) },
    { label: 'Z', color: '#2f6fd6', end: worldToScene([origin[0], origin[1], origin[2] + length]) },
  ]
  const start = worldToScene(origin)
  return <group>
    {axes.map((axis) => <group key={axis.label}>
      <Line points={[start, axis.end]} color={axis.color} lineWidth={3} />
      <TextLabel position={axis.end} text={axis.label} color={axis.color} heightPx={22} />
    </group>)}
  </group>
}

function CameraRig({ boundsKey, request }: { boundsKey: string; request: CameraRequest }) {
  // Read camera/controls through get() inside the effect: they are mutable three.js objects, not React state.
  const get = useThree((state) => state.get)
  const controlsReady = useThree((state) => state.controls !== null)
  useEffect(() => {
    const { camera, invalidate } = get()
    const controls = get().controls as unknown as { target: THREE.Vector3; update: () => void } | null
    const bounds = JSON.parse(boundsKey) as Aabb
    const { position, target } = cameraFor(bounds, request.preset)
    const span = Math.max(...bounds.max_m.map((value, axis) => value - bounds.min_m[axis]))
    camera.position.set(...position)
    camera.near = Math.max(0.01, span / 2000)
    camera.far = span * 20
    camera.updateProjectionMatrix()
    if (controls) {
      controls.target.set(...target)
      controls.update()
    } else {
      camera.lookAt(...target)
    }
    invalidate()
  }, [boundsKey, request, get, controlsReady])
  return null
}

export function Viewer3D({ project, route, selectedPipeId, selection, onSelect, focusRuleId: ruleId, onFocusRule: setRuleId, busy, solving, onSelectPipe, onSolve }: Props) {
  const [camera, setCamera] = useState<CameraRequest>({ preset: 'aerial', nonce: 0 })
  const [showTube, setShowTube] = useState(true)
  const [showSlabs, setShowSlabs] = useState(true)
  const model = useMemo(() => buildSceneModel(project, route, selectedPipeId), [project, route, selectedPipeId])
  const boundsKey = JSON.stringify(project.building.bounds_m)
  const rules = project.constraints
  const focusRuleId = rules.some((rule) => rule.id === ruleId) ? ruleId : ''
  const targets = useMemo(() => ruleTargetIds(project, focusRuleId || null), [project, focusRuleId])
  const focusRule = rules.find((rule) => rule.id === focusRuleId)
  const selected = selectionKey(selection)
  const selectedBox = model.boxes.find((box) => selectionKey(box.selection) === selected)
  const selectedPort = selection?.kind === 'port' ? model.ports.find((port) => port.id === selection.id) : undefined
  const [bx, by, bz] = model.bounds.size
  const gridSize = Math.max(bx, by, bz)
  let gridStep = project.routing_config.grid_resolution_m
  while (gridSize / gridStep > 120) gridStep *= 2
  const sceneRoute = model.route
  const connections = useMemo(() => project.pipes.flatMap((pipe) => {
    if (route?.status === 'SUCCESS' && route.pipe_id === pipe.id) return []
    const points = pipeConnectionPoints(project, pipe.id).map(worldToScene)
    return points.length > 1 ? [{ id: pipe.id, points }] : []
  }), [project, route])
  const portRadius = Math.max(0.12, Math.min(0.3, project.routing_config.grid_resolution_m * 0.6))

  return (
    <section className="viewer3d panel" aria-label="3D 보기">
      <div className="plan-heading">
        <div><h2>3D 건물·배관 보기</h2><p>객체를 클릭해 선택하세요. 2D와 선택·속성이 함께 바뀝니다.</p></div>
        <div className="plan-actions">
          <button type="button" className={camera.preset === 'aerial' ? 'tool active' : 'tool'} onClick={() => setCamera((value) => ({ preset: 'aerial', nonce: value.nonce + 1 }))}>조감도</button>
          <button type="button" className={camera.preset === 'plan' ? 'tool active' : 'tool'} onClick={() => setCamera((value) => ({ preset: 'plan', nonce: value.nonce + 1 }))}>평면도</button>
          <button type="button" className="button-secondary" onClick={() => setCamera((value) => ({ ...value, nonce: value.nonce + 1 }))}>카메라 리셋</button>
        </div>
      </div>
      <div className="plan-run viewer-run" role="group" aria-label="3D 경로 계산">
        <label>계산할 배관 <select aria-label="3D 계산할 배관" value={selectedPipeId} disabled={busy || !project.pipes.length} onChange={(event) => onSelectPipe(event.target.value)}>
          {!project.pipes.length && <option value="">배관을 먼저 연결하세요</option>}
          {project.pipes.map((pipe) => <option key={pipe.id} value={pipe.id}>{selectionLabel(project, { kind: 'pipe', id: pipe.id })}</option>)}
        </select></label>
        <button type="button" className="button-primary" disabled={busy || !project.pipes.some((pipe) => pipe.id === selectedPipeId)} onClick={onSolve}>{solving ? '계산 중…' : '경로 계산'}</button>
      </div>
      <RouteStatusNotice project={project} route={route} busy={busy} onSelect={onSelect} />
      <div className="viewer-toolbar">
        <label><input type="checkbox" checked={showTube} onChange={(event) => setShowTube(event.target.checked)} /> 배관 외경(보온 포함) 표시</label>
        <label><input type="checkbox" checked={showSlabs} onChange={(event) => setShowSlabs(event.target.checked)} /> 바닥판 표시</label>
        <label>규칙 대상 강조 <select value={focusRuleId} onChange={(event) => setRuleId(event.target.value)}>
          <option value="">선택 안 함</option>
          {rules.map((rule) => <option key={rule.id} value={rule.id}>{rule.id} · {rule.type} · {rule.status}</option>)}
        </select></label>
      </div>
      <div className="viewer-canvas">
        <Canvas
          frameloop="demand"
          camera={{ fov: 45, position: [0, 10, 10] }}
          fallback={<div className="viewer-fallback">이 브라우저에서는 WebGL을 사용할 수 없어 3D 보기를 표시할 수 없습니다.</div>}
        >
          <color attach="background" args={['#eef4f7']} />
          <ambientLight intensity={0.75} />
          <directionalLight position={[gridSize, gridSize * 1.5, gridSize * 0.6]} intensity={1.1} />
          <OrbitControls makeDefault enableDamping={false} />
          <CameraRig boundsKey={boundsKey} request={camera} />
          <FloorGrid bounds={project.building.bounds_m} step={gridStep} />
          <mesh geometry={unitBox} position={model.bounds.center} scale={model.bounds.size} raycast={noRaycast}>
            <meshBasicMaterial transparent opacity={0} depthWrite={false} />
            <Edges color="#92a9b6" />
          </mesh>
          <WorldAxes bounds={project.building.bounds_m} />
          {model.boxes.filter((box) => showSlabs || box.style !== 'slab').map((box) => (
            <BoxMesh
              key={selectionKey(box.selection)}
              box={box}
              selected={selectionKey(box.selection) === selected}
              ruleTarget={targets.has(box.selection.id)}
              onSelect={onSelect}
            />
          ))}
          {model.ports.map((port) => {
            const isSelected = selection?.kind === 'port' && selection.id === port.id
            const isTarget = targets.has(port.id)
            const roleColor = port.role ? ROLE_COLORS[port.role] : null
            return <group key={port.id}>
              <mesh
                geometry={unitSphere}
                position={port.center}
                scale={(isSelected ? 1.4 : 1) * (roleColor ? 1.5 : 1) * portRadius}
                onClick={(event: ThreeEvent<MouseEvent>) => { event.stopPropagation(); onSelect({ kind: 'port', id: port.id }) }}
                onPointerOver={(event: ThreeEvent<PointerEvent>) => { event.stopPropagation(); document.body.style.cursor = 'pointer' }}
                onPointerOut={() => { document.body.style.cursor = '' }}
              >
                <meshStandardMaterial color={roleColor ?? (isSelected ? SELECTED : isTarget ? RULE_TARGET : '#ffffff')} emissive={isSelected ? SELECTED : '#000000'} emissiveIntensity={0.3} />
              </mesh>
              <Line points={[port.center, port.tip]} color="#105c77" lineWidth={2} />
              {port.role && <TextLabel position={port.center} text={port.role === 'start' ? 'S' : 'E'} color="#ffffff" background={roleColor ?? undefined} heightPx={18} offsetPx={[14, 14]} />}
            </group>
          })}
          {model.waypoints.map((waypoint) => {
            const isSelected = selection?.kind === 'waypoint' && selection.id === waypoint.id
            return <group key={waypoint.id}>
              <mesh
                geometry={unitOctahedron}
                position={waypoint.center}
                scale={(isSelected ? 2.2 : 1.8) * portRadius}
                onClick={(event: ThreeEvent<MouseEvent>) => { event.stopPropagation(); onSelect({ kind: 'waypoint', id: waypoint.id }) }}
                onPointerOver={(event: ThreeEvent<PointerEvent>) => { event.stopPropagation(); document.body.style.cursor = 'pointer' }}
                onPointerOut={() => { document.body.style.cursor = '' }}
              >
                <meshStandardMaterial color={ROLE_COLORS.waypoint} emissive={isSelected ? SELECTED : '#000000'} emissiveIntensity={0.4} />
              </mesh>
              {waypoint.axis && <Line points={waypoint.axis} color={ROLE_COLORS.waypoint} lineWidth={2} dashed dashSize={0.15} gapSize={0.1} />}
              <TextLabel position={waypoint.center} text={String(waypoint.order)} color="#ffffff" background={isSelected ? SELECTED : ROLE_COLORS.waypoint} square heightPx={18} offsetPx={[14, 14]} />
            </group>
          })}
          {connections.map((connection) => <group key={connection.id}>
            <Line points={connection.points} color={selection?.kind === 'pipe' && selection.id === connection.id ? '#087fad' : '#63889b'} lineWidth={2} dashed dashSize={0.16} gapSize={0.12} onClick={(event: ThreeEvent<MouseEvent>) => { event.stopPropagation(); onSelect({ kind: 'pipe', id: connection.id }) }} />
          </group>)}
          {sceneRoute && <group>
            <Line points={sceneRoute.points} color="#06587a" lineWidth={2} onClick={(event: ThreeEvent<MouseEvent>) => { event.stopPropagation(); onSelect({ kind: 'pipe', id: sceneRoute.pipeId }) }} />
            {sceneRoute.segments.filter((segment) => segment.invalid).map((segment) => (
              <Line key={`invalid-${segment.index}`} points={[segment.from, segment.to]} color="#df4047" lineWidth={4} />
            ))}
            {showTube && sceneRoute.segments.map((segment) => <TubeSegment key={segment.index} segment={segment} radius={sceneRoute.radius} />)}
            {showTube && sceneRoute.points.slice(1, -1).map((point, index) => (
              <mesh key={`joint-${index}`} geometry={unitSphere} position={point} scale={sceneRoute.radius} raycast={noRaycast}>
                <meshStandardMaterial color="#1590bd" transparent opacity={0.85} />
              </mesh>
            ))}
          </group>}
          {selectedBox && <TextLabel position={[selectedBox.center[0], selectedBox.center[1] + selectedBox.size[1] / 2, selectedBox.center[2]]} text={selectionLabel(project, selectedBox.selection)} color="#ffffff" background="#0a789aee" offsetPx={[0, 16]} />}
          {selectedPort && <TextLabel position={selectedPort.center} text={selectionLabel(project, { kind: 'port', id: selectedPort.id })} color="#ffffff" background="#0a789aee" offsetPx={[0, -18]} />}
        </Canvas>
      </div>
      <div className="canvas-footer">
        <span>왼쪽 드래그 회전 · 오른쪽 드래그 이동 · 휠 확대/축소 · 클릭으로 선택</span>
        <strong>{selection ? `선택: ${selectionLabel(project, selection)}` : '선택 없음'}{sceneRoute ? ' · 계산된 경로' : ''}</strong>
      </div>
      {focusRule && <p className="viewer-rule">{focusRule.id} 대상: {focusRule.scope.target_ids.join(', ') || '없음'} · 배관 {focusRule.scope.pipe_ids.join(', ')} · 출처 {focusRule.source.document_id} {focusRule.source.clause_id} ({focusRule.source.source_type})</p>}
      <div className="plan-legend">
        <span><i className="legend-wall" /> 장애물</span>
        <span><i className="legend-slab" /> 바닥판</span>
        <span><i className="legend-keepout" /> KEEP_OUT Zone</span>
        <span><i className="legend-zone" /> 기타 Zone</span>
        <span><i className="legend-port" /> 연결점</span>
        <span><i className="legend-start" /> 시작점 S</span>
        <span><i className="legend-end" /> 끝점 E</span>
        <span><i className="legend-waypoint" /> 경유점(번호 = 순서)</span>
        <span>┄ 연결 표시 (미계산)</span><span><i className="legend-route" /> 계산된 경로</span>
        <span><i className="legend-invalid" /> 위반 구간</span>
        <span><i className="legend-selected" /> 선택</span>
        <span><i className="legend-target" /> 규칙 대상</span>
      </div>
    </section>
  )
}

export default Viewer3D
