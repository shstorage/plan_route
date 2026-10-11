import { useState, type FormEvent } from 'react'
import type { Constraint, EngineeringProject, Point3, Port } from '../api/client'
import {
  connectPort, createRule, updateBox, updatePort, updateRule,
  type NewRule, type RuleEdit, type Selection,
} from './model.ts'

type Props = {
  project: EngineeringProject
  selection: Selection | null
  selectedPipeId: string
  onCommit: (project: EngineeringProject) => void
  onError: (message: string) => void
}

type GeometryDraft = {
  minX: string; minY: string; minZ: string
  maxX: string; maxY: string; maxZ: string
  x: string; y: string; z: string
  orientation: Port['orientation']
}

const emptyGeometry: GeometryDraft = {
  minX: '', minY: '', minZ: '', maxX: '', maxY: '', maxZ: '',
  x: '', y: '', z: '', orientation: '+x',
}

function draftFor(project: EngineeringProject, selection: Selection | null): GeometryDraft {
  if (!selection) return emptyGeometry
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

const emptyNewRule: NewRule = {
  pipeId: '', targetId: '', type: 'KEEP_OUT', distanceText: '',
  documentId: '', revision: '', clauseId: '', evidence: '',
}

function draftForRule(rule: Constraint | undefined): RuleEdit {
  return {
    type: rule?.type ?? 'KEEP_OUT',
    status: rule?.status ?? 'draft',
    targetId: rule?.scope.target_ids[0] ?? '',
    distanceText: rule?.parameters.distance_m == null ? '' : String(rule.parameters.distance_m),
  }
}

export function EditorInspector({ project, selection, selectedPipeId, onCommit, onError }: Props) {
  const [geometry, setGeometry] = useState<GeometryDraft>(() => draftFor(project, selection))
  const [ruleId, setRuleId] = useState(() =>
    project.constraints.findLast((rule) => selection && rule.scope.target_ids.includes(selection.id))?.id
      ?? project.constraints[0]?.id ?? '')
  const [ruleEdit, setRuleEdit] = useState<RuleEdit>(() => draftForRule(project.constraints.find((rule) => rule.id === ruleId)))
  const [showNewRule, setShowNewRule] = useState(false)
  const [newRule, setNewRule] = useState<NewRule>(() => ({
      ...emptyNewRule,
      pipeId: selectedPipeId,
      targetId: selection?.id ?? '',
      type: selection?.kind === 'obstacle' ? 'MIN_CLEARANCE' : 'KEEP_OUT',
    }))

  const rule = project.constraints.find((item) => item.id === ruleId)

  function applyGeometry(event: FormEvent) {
    event.preventDefault()
    if (!selection) return
    try {
      if (selection.kind === 'port') {
        const point: Point3 = [numeric(geometry.x), numeric(geometry.y), numeric(geometry.z)]
        onCommit(updatePort(project, selection.id, point, geometry.orientation))
      } else {
        onCommit(updateBox(project, selection.kind, selection.id, {
          type: 'aabb',
          min_m: [numeric(geometry.minX), numeric(geometry.minY), numeric(geometry.minZ)],
          max_m: [numeric(geometry.maxX), numeric(geometry.maxY), numeric(geometry.maxZ)],
        }))
      }
    } catch (error) { onError(error instanceof Error ? error.message : '좌표를 변경하지 못했습니다.') }
  }

  function applyRule(event: FormEvent) {
    event.preventDefault()
    if (!rule) return
    try { onCommit(updateRule(project, rule.id, ruleEdit)) }
    catch (error) { onError(error instanceof Error ? error.message : '규칙을 변경하지 못했습니다.') }
  }

  function addRule(event: FormEvent) {
    event.preventDefault()
    try {
      const added = createRule(project, newRule)
      onCommit(added.project)
      setRuleId(added.id)
      setShowNewRule(false)
    } catch (error) { onError(error instanceof Error ? error.message : '규칙을 만들지 못했습니다.') }
  }

  const owner = selection?.kind === 'port'
    ? project.equipment.find((item) => item.ports.some((port) => port.id === selection.id))?.id
    : null
  const targetOptions = ruleEdit.type === 'KEEP_OUT'
    ? project.zones.map((item) => item.id)
    : [...project.zones, ...project.obstacles].map((item) => item.id)

  return (
    <aside className="editor-inspector" aria-label="도면 속성">
      <div className="inspector-heading"><span>속성</span><strong>{selection?.id ?? '객체 선택'}</strong></div>
      {!selection ? <p className="inspector-empty">도면에서 벽체, Zone 또는 Port를 선택하면 좌표와 속성을 변경할 수 있습니다.</p> : (
        <form onSubmit={applyGeometry} className="inspector-form">
          <div className="inspector-meta"><span>종류</span><strong>{selection.kind === 'obstacle' ? '장애물' : selection.kind === 'zone' ? '제약 Zone' : 'Port'}</strong></div>
          {owner && <div className="inspector-meta"><span>소유 장비</span><strong>{owner}</strong></div>}
          {selection.kind === 'port' ? (
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
          <button type="submit" className="button-secondary">좌표 적용</button>
        </form>
      )}
      {selection?.kind === 'port' && selectedPipeId && (
        <div className="port-connect">
          <span>{selectedPipeId} 연결</span>
          <button type="button" className="button-secondary" onClick={() => {
            try { onCommit(connectPort(project, selectedPipeId, 'from', selection.id)) }
            catch (error) { onError(error instanceof Error ? error.message : '시작 Port를 지정하지 못했습니다.') }
          }}>시작 Port로 지정</button>
          <button type="button" className="button-secondary" onClick={() => {
            try { onCommit(connectPort(project, selectedPipeId, 'to', selection.id)) }
            catch (error) { onError(error instanceof Error ? error.message : '도착 Port를 지정하지 못했습니다.') }
          }}>도착 Port로 지정</button>
        </div>
      )}

      <div className="inspector-divider" />
      <div className="inspector-heading"><span>Hard constraint</span><strong>제약 규칙</strong></div>
      {project.constraints.length ? (
        <>
          <label className="inspector-select">규칙 ID<select value={ruleId} onChange={(event) => { setRuleId(event.target.value); setRuleEdit(draftForRule(project.constraints.find((item) => item.id === event.target.value))) }}>
            {project.constraints.map((item) => <option key={item.id} value={item.id}>{item.id}</option>)}
          </select></label>
          {rule && <form onSubmit={applyRule} className="inspector-form">
            <label className="inspector-select">규칙 타입<select value={ruleEdit.type} onChange={(event) => {
              const type = event.target.value as Constraint['type']
              const options = type === 'KEEP_OUT' ? project.zones : [...project.zones, ...project.obstacles]
              setRuleEdit({ ...ruleEdit, type, targetId: options.some((item) => item.id === ruleEdit.targetId) ? ruleEdit.targetId : options[0]?.id ?? '' })
            }}><option value="KEEP_OUT">KEEP_OUT · 진입 금지</option><option value="MIN_CLEARANCE">MIN_CLEARANCE · 최소 이격</option></select></label>
            <label className="inspector-select">대상<select value={ruleEdit.targetId} onChange={(event) => setRuleEdit({ ...ruleEdit, targetId: event.target.value })}>
              {targetOptions.map((id) => <option key={id} value={id}>{id}</option>)}
            </select></label>
            {ruleEdit.type === 'MIN_CLEARANCE' && <label className="inspector-select">표면 이격거리 (m)<input type="number" min="0" step="any" value={ruleEdit.distanceText} onChange={(event) => setRuleEdit({ ...ruleEdit, distanceText: event.target.value })} /></label>}
            <label className="inspector-select">승인 상태<select value={ruleEdit.status} onChange={(event) => setRuleEdit({ ...ruleEdit, status: event.target.value as Constraint['status'] })}>
              <option value="draft">draft · 초안</option><option value="needs_review">needs_review · 검토 대기</option><option value="approved">approved · 승인</option><option value="rejected">rejected · 거부</option>
            </select></label>
            {ruleEdit.status !== 'approved' && <p className="rule-warning">미승인 규칙이 있는 배관은 실행되지 않습니다.</p>}
            <div className="rule-source">출처: {rule.source.document_id} · 개정 {rule.source.document_revision} · {rule.source.clause_id}</div>
            <button type="submit" className="button-secondary">규칙 적용</button>
          </form>}
        </>
      ) : <p className="inspector-empty">규칙이 없습니다.</p>}

      {selection?.kind === 'zone' || selection?.kind === 'obstacle' ? (
        <div className="new-rule">
          <button type="button" className="button-secondary" onClick={() => setShowNewRule((value) => !value)}>{showNewRule ? '규칙 추가 취소' : '선택 객체에 규칙 추가'}</button>
          {showNewRule && <form className="inspector-form" onSubmit={addRule}>
            <p className="rule-warning">새 규칙은 초안으로 저장됩니다. 출처를 입력한 뒤 상태를 직접 승인해야 경로에 적용됩니다.</p>
            <label className="inspector-select">배관<select value={newRule.pipeId} onChange={(event) => setNewRule({ ...newRule, pipeId: event.target.value })}>{project.pipes.map((pipe) => <option key={pipe.id} value={pipe.id}>{pipe.id}</option>)}</select></label>
            <label className="inspector-select">타입<select value={newRule.type} onChange={(event) => setNewRule({ ...newRule, type: event.target.value as Constraint['type'] })}><option value="KEEP_OUT" disabled={selection.kind === 'obstacle'}>KEEP_OUT</option><option value="MIN_CLEARANCE">MIN_CLEARANCE</option></select></label>
            {newRule.type === 'MIN_CLEARANCE' && <label className="inspector-select">표면 이격거리 (m)<input type="number" min="0" step="any" value={newRule.distanceText} onChange={(event) => setNewRule({ ...newRule, distanceText: event.target.value })} /></label>}
            <label className="inspector-select">문서 ID<input value={newRule.documentId} onChange={(event) => setNewRule({ ...newRule, documentId: event.target.value })} /></label>
            <label className="inspector-select">개정판<input value={newRule.revision} onChange={(event) => setNewRule({ ...newRule, revision: event.target.value })} /></label>
            <label className="inspector-select">조항 ID<input value={newRule.clauseId} onChange={(event) => setNewRule({ ...newRule, clauseId: event.target.value })} /></label>
            <label className="inspector-select">근거 문구<textarea rows={3} value={newRule.evidence} onChange={(event) => setNewRule({ ...newRule, evidence: event.target.value })} /></label>
            <button type="submit" className="button-primary">초안 규칙 만들기</button>
          </form>}
        </div>
      ) : null}
    </aside>
  )
}
