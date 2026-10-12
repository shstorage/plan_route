import { useState, type FormEvent } from 'react'
import type { EngineeringProject, Point3, Port } from '../api/client'
import { onTabKeyDown } from '../ui/tabs'
import {
  addEquipmentPort, changeEquipmentKind, connectPort, deleteEquipment, deleteObject, equipmentLabel, EQUIPMENT_KINDS,
  findWaypoint, metresToMillimetres, millimetresToMetres, reorderWaypoint, selectionLabel, updateBox, updatePipe, updatePort, updateWaypoint,
  type EquipmentKind, type Selection,
} from './model.ts'

type Props = {
  project: EngineeringProject; selection: Selection | null; selectedPipeId: string; busy: boolean
  onCommit: (project: EngineeringProject) => void; onError: (message: string) => void
  onSelect: (selection: Selection) => void; onAddPort: (equipmentId: string) => void
  onAddWaypoint: () => void; onConnect: (portId?: string) => void
  onFocusRule: (id: string) => void; onAddRule: (targetId: string) => void
}

const directions: Record<Port['orientation'], string> = {
  '+x': '오른쪽 (+X)', '-x': '왼쪽 (−X)', '+y': '위쪽 (+Y)', '-y': '아래쪽 (−Y)', '+z': '위층 (+Z)', '-z': '아래층 (−Z)',
}

function number(text: string): number {
  if (!text.trim() || !Number.isFinite(Number(text))) throw new Error('숫자를 확인해 주세요.')
  return Number(text)
}

function geometryDraft(project: EngineeringProject, selection: Selection | null) {
  const waypoint = selection?.kind === 'waypoint' ? findWaypoint(project, selection.id)?.waypoint : null
  const port = selection?.kind === 'port' ? project.equipment.flatMap((item) => item.ports).find((item) => item.id === selection.id) : null
  const shape = selection?.kind === 'obstacle' ? project.obstacles.find((item) => item.id === selection.id)?.shape
    : selection?.kind === 'zone' ? project.zones.find((item) => item.id === selection.id)?.shape : null
  return {
    position: (shape?.min_m ?? port?.position_m ?? waypoint?.position_m ?? [0, 0, 0]).map(String),
    size: shape ? shape.max_m.map((value, axis) => String(Number((value - shape.min_m[axis]).toFixed(9)))) : ['1', '1', '1'],
    orientation: port?.orientation ?? '+x', passAxis: waypoint?.pass_axis ?? '', note: waypoint?.note ?? '',
  }
}

export function ObjectInspector(props: Props) {
  const { project, selection, selectedPipeId, busy, onCommit, onError, onSelect, onAddPort, onConnect, onFocusRule, onAddRule } = props
  const [draft, setDraft] = useState(() => geometryDraft(project, selection))
  const [sourceProject, setSourceProject] = useState(project)
  if (sourceProject !== project) { setSourceProject(project); setDraft(geometryDraft(project, selection)) }
  const [section, setSection] = useState<'properties' | 'ports'>('properties')
  const bodyOwner = selection?.kind === 'obstacle' ? project.equipment.find((item) => item.geometry_ref === selection.id) : null
  const portOwner = selection?.kind === 'port' ? project.equipment.find((item) => item.ports.some((port) => port.id === selection.id)) : null
  const waypoint = selection?.kind === 'waypoint' ? findWaypoint(project, selection.id) : null
  const rules = selection ? project.constraints.filter((rule) => rule.scope.target_ids.includes(selection.id) || (selection.kind === 'pipe' && rule.scope.pipe_ids.includes(selection.id))) : []

  function change(action: () => EngineeringProject) {
    try { onCommit(action()) }
    catch (error) { onError(error instanceof Error ? error.message : '변경하지 못했습니다.') }
  }

  function apply(event: FormEvent) {
    event.preventDefault()
    if (!selection || selection.kind === 'pipe') return
    try {
      const position = draft.position.map(number) as Point3
      if (selection.kind === 'port') onCommit(updatePort(project, selection.id, position, draft.orientation))
      else if (selection.kind === 'waypoint') onCommit(updateWaypoint(project, selection.id, { position, passAxis: draft.passAxis ? draft.passAxis as 'x' | 'y' | 'z' : null, note: draft.note }))
      else {
        const size = draft.size.map(number)
        onCommit(updateBox(project, selection.kind, selection.id, { type: 'aabb', min_m: position, max_m: position.map((value, axis) => value + size[axis]) as Point3 }))
      }
    } catch (error) {
      onError(error instanceof Error ? error.message : '입력값을 확인해 주세요.')
      setDraft(geometryDraft(project, selection))
    }
  }

  return <aside className="editor-inspector" aria-label="선택한 객체 속성">
    <div className="inspector-heading"><span>선택한 객체</span><strong>{selection ? selectionLabel(project, selection) : '객체를 선택하세요'}</strong></div>
    {!selection ? <p className="inspector-empty">도면의 기기·연결점·배관을 클릭하면 여기서 수정할 수 있습니다. 처음에는 기기를 배치하고 ‘배관 연결’을 눌러 보세요.</p>
      : selection.kind === 'pipe' ? <PipeInspector key={JSON.stringify(project.pipes.find((pipe) => pipe.id === selection.id))} {...props} pipeId={selection.id} /> : <>
        {bodyOwner && <div className="inspector-tabs" role="tablist" aria-label="기기 속성 항목" onKeyDown={onTabKeyDown}>
          <button role="tab" aria-selected={section === 'properties'} tabIndex={section === 'properties' ? 0 : -1} type="button" onClick={() => setSection('properties')}>속성</button>
          <button role="tab" aria-selected={section === 'ports'} tabIndex={section === 'ports' ? 0 : -1} type="button" onClick={() => setSection('ports')}>연결점 ({bodyOwner.ports.length})</button>
        </div>}
        <div hidden={!!bodyOwner && section !== 'properties'}>
        {bodyOwner && <label className="inspector-select inspector-kind">기기 종류<select aria-label="기기 종류" value={bodyOwner.kind} disabled={busy} onChange={(event) => change(() => changeEquipmentKind(project, bodyOwner.id, event.target.value as EquipmentKind))}>
          {!(bodyOwner.kind in EQUIPMENT_KINDS) && <option value={bodyOwner.kind}>{bodyOwner.kind}</option>}
          {Object.entries(EQUIPMENT_KINDS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select></label>}
        {portOwner && <p className="inspector-empty">소속 기기: {equipmentLabel(project, portOwner.id)}</p>}
        <form onSubmit={apply} className="inspector-form"><fieldset disabled={busy} className="inspector-fieldset">
          <span className="inspector-section-title">위치 (m)</span>
          <div className="inspector-fields three">{['X', 'Y', 'Z'].map((axis, index) => <label key={axis}>{axis}<input aria-label={`${axis} 위치`} type="number" step="any" value={draft.position[index]} onChange={(event) => setDraft({ ...draft, position: draft.position.map((value, i) => i === index ? event.target.value : value) })} /></label>)}</div>
          {(selection.kind === 'obstacle' || selection.kind === 'zone') && <>
            <span className="inspector-section-title">크기 (m)</span>
            <div className="inspector-fields three">{['폭', '깊이', '높이'].map((label, index) => <label key={label}>{label}<input aria-label={label} type="number" min="0.1" step="any" value={draft.size[index]} onChange={(event) => setDraft({ ...draft, size: draft.size.map((value, i) => i === index ? event.target.value : value) })} /></label>)}</div>
            <p className="inspector-empty">위치는 왼쪽 아래·바닥 기준입니다.</p>
          </>}
          {selection.kind === 'port' && <label className="inspector-select">바깥으로 향하는 방향<select aria-label="연결점 방향" value={draft.orientation} onChange={(event) => setDraft({ ...draft, orientation: event.target.value as Port['orientation'] })}>{Object.entries(directions).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>}
          {selection.kind === 'waypoint' && <label className="inspector-select">통과 방향<select value={draft.passAxis} onChange={(event) => setDraft({ ...draft, passAxis: event.target.value })}><option value="">지나가기만 함</option>{['x', 'y', 'z'].map((axis) => <option key={axis} value={axis}>{axis.toUpperCase()} 방향으로 곧게 통과</option>)}</select></label>}
          <button type="submit" className="button-secondary">수정 적용</button>
        </fieldset></form>
        </div>
        {bodyOwner && <div hidden={section !== 'ports'}><EquipmentPorts project={project} equipmentId={bodyOwner.id} busy={busy} onCommit={onCommit} onError={onError} onSelect={onSelect} onAddPort={onAddPort} /></div>}
        {portOwner?.geometry_ref && <button type="button" className="button-ghost inspector-kind" onClick={() => onSelect({ kind: 'obstacle', id: portOwner.geometry_ref! })}>← 소속 기기 속성</button>}
        {selection.kind === 'port' && <button type="button" className="button-secondary inspector-kind" disabled={busy} onClick={() => onConnect(selection.id)}>이 연결점에서 배관 연결</button>}
        {selection.kind === 'zone' && <button type="button" className="button-secondary inspector-kind" disabled={busy} onClick={() => onAddRule(selection.id)}>이 구역에 제약 설정</button>}
        <button type="button" className="button-danger inspector-delete" disabled={busy} onClick={() => change(() => bodyOwner ? deleteEquipment(project, bodyOwner.id) : deleteObject(project, selection))}>{bodyOwner ? '기기 삭제' : selection.kind === 'port' ? '연결점 삭제' : '삭제'}</button>
      </>}
    {selection && <details className="inspector-details"><summary>상세 정보 · 제약</summary>
      <p className="inspector-empty">내부 ID: {selection.id}{bodyOwner ? ` · 기기 ID: ${bodyOwner.id}` : ''}</p>
      {waypoint && <p className="inspector-empty">순서 {waypoint.index + 1} · {selectionLabel(project, { kind: 'pipe', id: waypoint.pipe.id })}</p>}
      {waypoint && <div className="inspector-actions"><button type="button" className="button-secondary" disabled={busy || waypoint.index === 0} onClick={() => change(() => reorderWaypoint(project, waypoint.waypoint.id, -1))}>앞으로</button><button type="button" className="button-secondary" disabled={busy || waypoint.index === (waypoint.pipe.waypoints?.length ?? 0) - 1} onClick={() => change(() => reorderWaypoint(project, waypoint.waypoint.id, 1))}>뒤로</button></div>}
      {selection.kind === 'waypoint' && <label className="inspector-select">메모<input disabled={busy} maxLength={500} value={draft.note} onChange={(event) => setDraft({ ...draft, note: event.target.value })} /><small>메모 변경 후 수정 적용을 누르세요.</small></label>}
      {rules.map((rule) => <button className="button-secondary inspector-kind" type="button" key={rule.id} disabled={busy} onClick={() => onFocusRule(rule.id)}>{rule.type === 'KEEP_OUT' ? '진입 금지' : `최소 이격 ${rule.parameters.distance_m} m`} · {rule.status === 'approved' ? '승인' : '미승인'}</button>)}
      {(selection.kind === 'obstacle') && <button type="button" className="button-secondary" disabled={busy} onClick={() => onAddRule(selection.id)}>이 형상에 제약 설정</button>}
      {selection.kind === 'port' && project.pipes.some((pipe) => pipe.id === selectedPipeId) && <div className="inspector-stack"><span>선택 배관의 연결점 바꾸기</span>{(['from', 'to'] as const).map((endpoint) => <button type="button" className="button-secondary" key={endpoint} disabled={busy} onClick={() => change(() => connectPort(project, selectedPipeId, endpoint, selection.id))}>{endpoint === 'from' ? '시작으로 지정' : '도착으로 지정'}</button>)}</div>}
    </details>}
  </aside>
}

function EquipmentPorts({ project, equipmentId, busy, onCommit, onError, onSelect }: Pick<Props, 'project' | 'busy' | 'onCommit' | 'onError' | 'onSelect' | 'onAddPort'> & { equipmentId: string }) {
  const equipment = project.equipment.find((item) => item.id === equipmentId)!
  const [adding, setAdding] = useState(false)
  const [position, setPosition] = useState(() => equipment.ports[0].position_m.map(String))
  const [orientation, setOrientation] = useState<Port['orientation']>('+x')
  return <section className="equipment-ports" aria-label="기기 연결점 관리">
    <p className="inspector-empty">노즐마다 연결점을 둘 수 있습니다. 목록을 클릭해 위치·방향을 수정하세요.</p>
    <ul className="nozzle-list">{equipment.ports.map((port, index) => {
      const connected = project.pipes.some((pipe) => pipe.from_port_id === port.id || pipe.to_port_id === port.id)
      const blocked = connected || equipment.ports.length === 1
      return <li key={port.id}>
        <button className="nozzle-select" type="button" disabled={busy} onClick={() => onSelect({ kind: 'port', id: port.id })}><strong>연결점 {index + 1}</strong><small>{directions[port.orientation]}{connected ? ' · 연결됨' : ''}</small></button>
        <button className="button-ghost" type="button" aria-label={`연결점 ${index + 1} 삭제`} title={connected ? '배관을 먼저 삭제하거나 연결점을 바꾸세요.' : equipment.ports.length === 1 ? '기기에는 연결점이 하나 이상 필요합니다.' : '연결점 삭제'} disabled={busy || blocked} onClick={() => {
          try { onCommit(deleteObject(project, { kind: 'port', id: port.id })) }
          catch (error) { onError(error instanceof Error ? error.message : '삭제하지 못했습니다.') }
        }}>×</button>
      </li>
    })}</ul>
    <button className="button-secondary" type="button" disabled={busy} onClick={() => setAdding(!adding)}>+ 연결점 추가</button>
    {adding && <form className="inspector-form" onSubmit={(event) => {
      event.preventDefault()
      try {
        const added = addEquipmentPort(project, equipmentId, position.map(number) as Point3, orientation)
        onCommit(added.project)
        onSelect(added.selection)
      } catch (error) { onError(error instanceof Error ? error.message : '연결점을 추가하지 못했습니다.') }
    }}><fieldset className="inspector-fieldset" disabled={busy}>
      <span className="inspector-section-title">새 연결점 위치 (m)</span>
      <div className="inspector-fields three">{['X', 'Y', 'Z'].map((axis, index) => <label key={axis}>{axis}<input aria-label={`새 연결점 ${axis}`} type="number" step="any" value={position[index]} onChange={(event) => setPosition(position.map((value, i) => i === index ? event.target.value : value))} /></label>)}</div>
      <label className="inspector-select">방향<select aria-label="새 연결점 방향" value={orientation} onChange={(event) => setOrientation(event.target.value as Port['orientation'])}>{Object.entries(directions).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <p className="inspector-empty">배관이 출발할 수 있는 몸체 바깥 위치를 지정하세요. 접속 표시용 점이며 노즐 형상은 아닙니다.</p>
      <div className="inspector-actions"><button className="button-secondary" type="submit">연결점 만들기</button><button className="button-ghost" type="button" onClick={() => setAdding(false)}>취소</button></div>
    </fieldset></form>}
    <p className="inspector-empty">연결된 점은 배관을 먼저 해제해야 삭제할 수 있고, 기기에는 연결점이 최소 하나 필요합니다.</p>
  </section>
}

function PipeInspector({ project, pipeId, busy, onCommit, onError, onAddWaypoint, onSelect }: Props & { pipeId: string }) {
  const pipe = project.pipes.find((item) => item.id === pipeId)
  const [values, setValues] = useState(() => [pipe?.outer_diameter_m ?? 0.1, pipe?.insulation_thickness_m ?? 0, pipe?.clearance_margin_m ?? 0].map((value) => String(metresToMillimetres(value))))
  if (!pipe) return <p>배관이 없습니다.</p>
  function change(action: () => EngineeringProject) {
    try { onCommit(action()) } catch (error) { onError(error instanceof Error ? error.message : '변경하지 못했습니다.') }
  }
  return <>
    <p className="inspector-empty">{selectionLabel(project, { kind: 'port', id: pipe.from_port_id })}<br />↓<br />{selectionLabel(project, { kind: 'port', id: pipe.to_port_id })}</p>
    <form className="inspector-form" onSubmit={(event) => { event.preventDefault(); change(() => updatePipe(project, pipe.id, { outerDiameterText: millimetresToMetres(values[0]), insulationText: millimetresToMetres(values[1]), marginText: millimetresToMetres(values[2]) })) }}>
      <fieldset disabled={busy} className="inspector-fieldset">{['외경 (mm)', '보온재 두께 (mm)'].map((label, index) => <label className="inspector-select" key={label}>{label}<input aria-label={label} type="number" min="0" step="any" value={values[index]} onChange={(event) => setValues(values.map((value, i) => i === index ? event.target.value : value))} /></label>)}
        <details className="inspector-details"><summary>추가 여유 두께</summary><label className="inspector-select">마진 (mm)<input type="number" min="0" step="any" value={values[2]} onChange={(event) => setValues([values[0], values[1], event.target.value])} /></label></details>
        <button type="submit" className="button-secondary">단면 적용</button>
      </fieldset>
    </form>
    <div className="inspector-stack inspector-kind"><button type="button" className="button-secondary" disabled={busy} onClick={onAddWaypoint}>+ 경유점 추가 · 도면 클릭</button>
      {(pipe.waypoints ?? []).map((waypoint, index) => <button type="button" className="button-secondary" key={waypoint.id} disabled={busy} onClick={() => onSelect({ kind: 'waypoint', id: waypoint.id })}>경유점 {index + 1} 수정</button>)}
    </div>
    <button type="button" className="button-danger inspector-delete" disabled={busy} onClick={() => change(() => deleteObject(project, { kind: 'pipe', id: pipeId }))}>배관 삭제</button>
  </>
}
