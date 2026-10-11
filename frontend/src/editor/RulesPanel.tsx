import { useState, type FormEvent } from 'react'
import type { Constraint, EngineeringProject } from '../api/client'
import {
  RULE_STATUS_TEXT, RULE_TYPE_TEXT, createRule, defaultRuleSource, deleteRule, describeRule, missingForNewRule, ruleEffect, ruleTargetOptions, updateRule,
  type NewRule, type RuleEdit,
} from './model.ts'

type Props = {
  project: EngineeringProject
  selectedPipeId: string
  busy: boolean
  /** Rule whose targets are highlighted in 2D and 3D; also the rule open for editing. */
  focusRuleId: string
  onFocusRule: (ruleId: string) => void
  /** Set by the inspector's "add rule for this object"; a new nonce opens the form with that target. */
  newRuleRequest: { targetId: string; nonce: number } | null
  onCommit: (project: EngineeringProject) => void
  onApproveRule: (project: EngineeringProject, ruleId: string, reviewer: string) => void
}

const AUTO_SOURCE_KEY = 'plan_route.autoRuleSource'

function readAutoSource(): boolean {
  try { return window.localStorage.getItem(AUTO_SOURCE_KEY) !== 'off' } catch { return true }
}

function writeAutoSource(on: boolean) {
  try { window.localStorage.setItem(AUTO_SOURCE_KEY, on ? 'on' : 'off') } catch { /* storage unavailable: keep in-memory choice */ }
}

const effectText = {
  applied: '적용 중',
  blocking: '실행 차단 · 미승인',
  'other-pipe': '다른 배관',
  ignored: '',
} as const

function editFor(rule: Constraint): RuleEdit {
  return {
    type: rule.type,
    status: rule.status,
    pipeIds: [...rule.scope.pipe_ids],
    targetIds: [...rule.scope.target_ids],
    distanceText: rule.parameters.distance_m == null ? '' : String(rule.parameters.distance_m),
  }
}

function toggle(list: string[], id: string): string[] {
  return list.includes(id) ? list.filter((item) => item !== id) : [...list, id]
}

function ScopePicker({ project, type, pipeIds, targetIds, onChange }: {
  project: EngineeringProject
  type: Constraint['type']
  pipeIds: string[]
  targetIds: string[]
  onChange: (pipeIds: string[], targetIds: string[]) => void
}) {
  const allowed = new Set(ruleTargetOptions(project, type))
  const groups = [
    { label: 'Zone', ids: project.zones.map((item) => item.id) },
    { label: type === 'KEEP_OUT' ? '장애물 (진입 금지는 Zone만 가능)' : '장애물', ids: project.obstacles.map((item) => item.id) },
  ]
  return <>
    <fieldset className="rule-pick">
      <legend>적용 배관 <small>{pipeIds.length}개</small></legend>
      {project.pipes.map((pipe) => <label key={pipe.id}><input type="checkbox" checked={pipeIds.includes(pipe.id)} onChange={() => onChange(toggle(pipeIds, pipe.id), targetIds)} />{pipe.id}</label>)}
    </fieldset>
    <fieldset className="rule-pick targets">
      <legend>대상 <small>{targetIds.length}개</small></legend>
      {groups.map((group) => <div key={group.label} className="rule-pick-group">
        <span>{group.label}</span>
        {group.ids.map((id) => <label key={id} className={allowed.has(id) ? '' : 'disabled'}>
          <input type="checkbox" disabled={!allowed.has(id)} checked={targetIds.includes(id)} onChange={() => onChange(pipeIds, toggle(targetIds, id))} />{id}
        </label>)}
      </div>)}
    </fieldset>
  </>
}

function RuleTypeFields({ type, distanceText, onType, onDistance }: {
  type: Constraint['type']; distanceText: string
  onType: (type: Constraint['type']) => void; onDistance: (text: string) => void
}) {
  return <div className="rule-type-fields">
    <label>규칙 종류<select value={type} onChange={(event) => onType(event.target.value as Constraint['type'])}>
      <option value="KEEP_OUT">진입 금지 (KEEP_OUT)</option>
      <option value="MIN_CLEARANCE">최소 이격 (MIN_CLEARANCE)</option>
    </select></label>
    {type === 'MIN_CLEARANCE' && <label>표면 간 최소 거리 (m)<input type="number" min="0" step="any" value={distanceText} onChange={(event) => onDistance(event.target.value)} /></label>}
    <p className="rule-type-help">{RULE_TYPE_TEXT[type].meaning}</p>
  </div>
}

function RuleEditor({ project, rule, busy, onCommit, onDeleted, onApproveRule }: {
  project: EngineeringProject; rule: Constraint; busy: boolean
  onCommit: (project: EngineeringProject) => void; onDeleted: () => void
  onApproveRule: Props['onApproveRule']
}) {
  const [edit, setEdit] = useState<RuleEdit>(() => editFor(rule))
  const [error, setError] = useState('')
  const [reviewer, setReviewer] = useState('')

  function apply(event: FormEvent) {
    event.preventDefault()
    try {
      const changed = updateRule(project, rule.id, edit)
      if (edit.status === 'approved') {
        if (!reviewer.trim()) throw new Error('현재 규칙을 승인할 검토자 이름을 입력해 주세요.')
        onApproveRule(changed, rule.id, reviewer.trim())
      } else onCommit(changed)
      setError('')
    } catch (failure) {
      // Shown next to the button: the canvas error banner is usually scrolled out of view here.
      setError(failure instanceof Error ? failure.message : '규칙을 변경하지 못했습니다.')
    }
  }

  return <form className="rule-editor" onSubmit={apply}>
    <RuleTypeFields type={edit.type} distanceText={edit.distanceText}
      onType={(type) => setEdit({ ...edit, type, targetIds: edit.targetIds.filter((id) => ruleTargetOptions(project, type).includes(id)) })}
      onDistance={(distanceText) => setEdit({ ...edit, distanceText })} />
    <ScopePicker project={project} type={edit.type} pipeIds={edit.pipeIds} targetIds={edit.targetIds} onChange={(pipeIds, targetIds) => setEdit({ ...edit, pipeIds, targetIds })} />
    <label className="rule-status">승인 상태<select value={edit.status} onChange={(event) => setEdit({ ...edit, status: event.target.value as Constraint['status'] })}>
      {(Object.keys(RULE_STATUS_TEXT) as Constraint['status'][]).map((status) => <option key={status} value={status}>{RULE_STATUS_TEXT[status]} ({status})</option>)}
    </select></label>
    {edit.status === 'approved' && <label>승인 검토자 이름
      <input value={reviewer} onChange={(event) => setReviewer(event.target.value)} maxLength={100} required />
      <small>현재 개정의 내용을 확인하고 승인합니다. 수정된 규칙에는 이전 승인이 재사용되지 않습니다.</small>
    </label>}
    <p className="rule-source">규칙 개정 {rule.definition_revision ?? 1} · {rule.approved_content_sha256 ? '내용에 연결된 승인' : '내용 연결 승인 없음'}
      {rule.approved_by && ` · ${rule.approved_by} · ${rule.approved_at ?? ''}`}</p>
    <p className="rule-source">출처: {rule.source.document_id} · 개정 {rule.source.document_revision} · {rule.source.clause_id} ({rule.source.source_type})<br />근거: {rule.source.evidence_text}</p>
    <div className="rule-actions">
      <button type="submit" className="button-secondary" disabled={busy}>{edit.status === 'approved' ? '현재 내용 승인·적용' : '규칙 적용'}</button>
      <button type="button" className="button-danger" disabled={busy} onClick={() => {
        try { onCommit(deleteRule(project, rule.id)); onDeleted() }
        catch (failure) { setError(failure instanceof Error ? failure.message : '규칙을 삭제하지 못했습니다.') }
      }}>규칙 삭제</button>
      {error && <span className="rule-error" role="alert">반영되지 않음: {error}</span>}
    </div>
  </form>
}

const SYNTHETIC_HINT = '문서 SYNTH-ASSUMPTION · 개정 1 · 조항 A-번호 · 근거는 규칙 내용으로 생성, 끄면 직접 수정'

function NewRuleForm({ project, initial, busy, onCreated, onCancel, onCommit }: {
  project: EngineeringProject; initial: NewRule; busy: boolean
  onCreated: (id: string) => void; onCancel: () => void
  onCommit: (project: EngineeringProject) => void
}) {
  const [manual, setManual] = useState<NewRule>(initial)
  const [autoSource, setAutoSource] = useState(readAutoSource)
  const [error, setError] = useState('')
  // With the option on, provenance follows the rule being drawn up and is shown read-only.
  const rule: NewRule = autoSource ? { ...manual, ...defaultRuleSource(project, manual) } : manual
  const setRule = (next: NewRule) => setManual(next)
  const missing = missingForNewRule(rule)

  function submit(event: FormEvent) {
    event.preventDefault()
    try {
      const added = createRule(project, rule)
      onCommit(added.project)
      onCreated(added.id)
    } catch (failure) { setError(failure instanceof Error ? failure.message : '규칙을 만들지 못했습니다.') }
  }

  return <form className="rule-editor new" onSubmit={submit}>
    <p className="rule-warning">새 규칙은 <b>초안</b>으로 저장됩니다. 만든 뒤 승인 상태를 직접 ‘승인’으로 바꿔야 경로 계산에 적용됩니다.</p>
    <RuleTypeFields type={rule.type} distanceText={rule.distanceText}
      onType={(type) => setRule({ ...rule, type, targetIds: rule.targetIds.filter((id) => ruleTargetOptions(project, type).includes(id)) })}
      onDistance={(distanceText) => setRule({ ...rule, distanceText })} />
    <ScopePicker project={project} type={rule.type} pipeIds={rule.pipeIds} targetIds={rule.targetIds} onChange={(pipeIds, targetIds) => setRule({ ...rule, pipeIds, targetIds })} />
    <label className="rule-auto-source">
      <input type="checkbox" checked={autoSource} onChange={(event) => {
        const on = event.target.checked
        setAutoSource(on)
        writeAutoSource(on)
        // Turning it off keeps the generated values as an editable starting point.
        if (!on) setManual(rule)
      }} />
      출처를 연구용 가정 기본값으로 자동 채우기 <small>({SYNTHETIC_HINT})</small>
    </label>
    <div className={`rule-source-fields${autoSource ? ' auto' : ''}`}>
      <label>문서 ID *<input value={rule.documentId} readOnly={autoSource} placeholder="예: STUDY-01" onChange={(event) => setRule({ ...rule, documentId: event.target.value })} /></label>
      <label>개정판 *<input value={rule.revision} readOnly={autoSource} placeholder="예: 1" onChange={(event) => setRule({ ...rule, revision: event.target.value })} /></label>
      <label>조항 ID *<input value={rule.clauseId} readOnly={autoSource} placeholder="예: A-1" onChange={(event) => setRule({ ...rule, clauseId: event.target.value })} /></label>
      <label className="wide">근거 문구 *<textarea rows={2} value={rule.evidence} readOnly={autoSource} placeholder="예: 연구용 가정 – 케이블트레이와 0.5 m 이격" onChange={(event) => setRule({ ...rule, evidence: event.target.value })} /></label>
    </div>
    <div className="rule-actions">
      <button type="submit" className="button-primary" disabled={busy}>초안 규칙 만들기</button>
      <button type="button" className="button-secondary" onClick={onCancel}>취소</button>
      {error ? <span className="rule-error" role="alert">만들지 못함: {error}</span>
        : missing.length > 0 && <span className="rule-missing">아직 필요한 항목: {missing.join(', ')}</span>}
    </div>
  </form>
}

export function RulesPanel({
  project, selectedPipeId, busy, focusRuleId, onFocusRule, newRuleRequest, onCommit, onApproveRule,
}: Props) {
  const [creating, setCreating] = useState<NewRule | null>(null)
  const [creatingKey, setCreatingKey] = useState(0)
  const [handledRequest, setHandledRequest] = useState(newRuleRequest?.nonce ?? 0)
  if (newRuleRequest && newRuleRequest.nonce !== handledRequest) {
    const isObstacle = project.obstacles.some((item) => item.id === newRuleRequest.targetId)
    setHandledRequest(newRuleRequest.nonce)
    setCreating({
      pipeIds: selectedPipeId ? [selectedPipeId] : [], targetIds: [newRuleRequest.targetId],
      type: isObstacle ? 'MIN_CLEARANCE' : 'KEEP_OUT', distanceText: '',
      documentId: '', revision: '', clauseId: '', evidence: '',
    })
    setCreatingKey((value) => value + 1)
  }

  const order = { applied: 0, blocking: 0, 'other-pipe': 1, ignored: 2 }
  const rules = [...project.constraints].sort((a, b) => order[ruleEffect(a, selectedPipeId)] - order[ruleEffect(b, selectedPipeId)])
  const applied = rules.filter((rule) => ruleEffect(rule, selectedPipeId) === 'applied')
  const blocking = rules.filter((rule) => ruleEffect(rule, selectedPipeId) === 'blocking')

  return (
    <section className="rules-panel" aria-label="제약 규칙">
      <div className="rules-heading">
        <div>
          <span className="rules-eyebrow">HARD CONSTRAINTS</span>
          <h3>제약 규칙 <small>{project.constraints.length}개</small></h3>
        </div>
        <p className={`rules-summary${blocking.length ? ' bad' : ''}`}>
          {selectedPipeId ? <>
            <b>{selectedPipeId}</b>에는 승인 규칙 <b>{applied.length}개</b>가 <b>모두 동시에</b> 적용됩니다.
            {blocking.length > 0 && <> 미승인 규칙 {blocking.length}개({blocking.map((rule) => rule.id).join(', ')}) 때문에 지금은 계산이 거부됩니다.</>}
          </> : '배관을 선택하세요.'}
        </p>
        <button type="button" className="button-secondary" disabled={busy} onClick={() => {
          setCreating({
            pipeIds: selectedPipeId ? [selectedPipeId] : [], targetIds: [], type: 'MIN_CLEARANCE', distanceText: '',
            documentId: '', revision: '', clauseId: '', evidence: '',
          })
          setCreatingKey((value) => value + 1)
        }}>+ 규칙 추가</button>
      </div>
      <details className="rules-help">
        <summary>규칙은 어떻게 적용되나요?</summary>
        <ul>
          <li><b>진입 금지</b>: {RULE_TYPE_TEXT.KEEP_OUT.meaning}</li>
          <li><b>최소 이격</b>: {RULE_TYPE_TEXT.MIN_CLEARANCE.meaning} 배관마다, 대상마다 거리를 다르게 하려면 규칙을 따로 만드세요.</li>
          <li>한 배관에 걸린 <b>승인</b> 규칙은 개수와 관계없이 <b>모두 함께</b>(AND) 적용됩니다. 벽·장애물과의 물리적 충돌은 규칙 없이도 항상 막힙니다.</li>
          <li>배관에 초안·검토 대기·거부 상태 규칙이 하나라도 있으면 그 배관은 계산하지 않습니다(승인되지 않은 조건을 몰래 빼고 계산하지 않기 위함). 쓰지 않을 규칙은 삭제하거나 배관 선택을 해제하세요.</li>
          <li>모든 수치는 연구용 가정값이며 실제 법규·설계기준 값이 아닙니다.</li>
        </ul>
      </details>
      {creating && <NewRuleForm key={creatingKey} project={project} initial={creating} busy={busy} onCommit={onCommit}
        onCancel={() => setCreating(null)} onCreated={(id) => { setCreating(null); onFocusRule(id) }} />}
      <ul className="rule-list">
        {rules.map((rule) => {
          const effect = ruleEffect(rule, selectedPipeId)
          const open = focusRuleId === rule.id
          return <li key={rule.id} className={`rule-row effect-${effect}${open ? ' open' : ''}`}>
            <button type="button" className="rule-summary" aria-expanded={open} onClick={() => onFocusRule(open ? '' : rule.id)}>
              <span className={`effect-badge ${effect}`}>{effectText[effect]}</span>
              <span className={`type-badge ${rule.type}`}>{RULE_TYPE_TEXT[rule.type].name}{rule.type === 'MIN_CLEARANCE' && ` ${rule.parameters.distance_m} m`}</span>
              <span className="rule-sentence">{describeRule(rule)}</span>
              <span className="rule-meta">{rule.id} · {RULE_STATUS_TEXT[rule.status]}</span>
            </button>
            {open && <RuleEditor key={JSON.stringify(rule)} project={project} rule={rule} busy={busy} onCommit={onCommit} onApproveRule={onApproveRule} onDeleted={() => onFocusRule('')} />}
          </li>
        })}
        {!rules.length && <li className="rule-empty">규칙이 없습니다. ‘+ 규칙 추가’로 만들 수 있습니다.</li>}
      </ul>
    </section>
  )
}
