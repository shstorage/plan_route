import { useState, type FormEvent } from 'react'
import type { EngineeringProject, Pipe, Point3 } from '../api/client'
import {
  CELL_LIMIT, CELL_WARNING, gridCellCount, metresToMillimetres, millimetresToMetres,
  pipeEnvelopeDiameter, updateDomain, updatePipe, type DomainEdit,
} from './model.ts'

type CommonProps = {
  project: EngineeringProject
  busy: boolean
  open: boolean
  onToggle: (open: boolean) => void
  onCommit: (project: EngineeringProject) => void
  onError: (message: string) => void
}

const axes = ['X', 'Y', 'Z'] as const

function domainDraft(project: EngineeringProject): DomainEdit {
  const bounds = project.building.bounds_m
  return {
    minText: bounds.min_m.map(String) as DomainEdit['minText'],
    maxText: bounds.max_m.map(String) as DomainEdit['maxText'],
    floors: project.building.floors.map((floor) => ({ id: floor.id, zMinText: String(floor.z_min_m), zMaxText: String(floor.z_max_m) })),
    gridText: String(project.routing_config.grid_resolution_m),
  }
}

function previewCells(edit: DomainEdit): number | null {
  const min = edit.minText.map(Number) as Point3
  const max = edit.maxText.map(Number) as Point3
  const grid = Number(edit.gridText)
  const texts = [...edit.minText, ...edit.maxText, edit.gridText]
  if (texts.some((text) => !text.trim()) || ![...min, ...max, grid].every(Number.isFinite) || grid <= 0) return null
  if (min.some((value, axis) => max[axis] <= value)) return null
  return gridCellCount(min, max, grid)
}

function formatSize(project: EngineeringProject): string {
  const { min_m: min, max_m: max } = project.building.bounds_m
  return axes.map((_, axis) => Number((max[axis] - min[axis]).toFixed(6))).join(' × ')
}

export function DomainSettings({ project, busy, open, onToggle, onCommit, onError }: CommonProps) {
  const sourceKey = JSON.stringify([project.building, project.routing_config.grid_resolution_m])
  const [draft, setDraft] = useState(() => ({ sourceKey, edit: domainDraft(project) }))
  // Reset the inputs when the stored domain changes (apply, undo, load) without remounting the card.
  if (draft.sourceKey !== sourceKey) setDraft({ sourceKey, edit: domainDraft(project) })
  const edit = draft.sourceKey === sourceKey ? draft.edit : domainDraft(project)
  const setEdit = (next: DomainEdit) => setDraft({ sourceKey, edit: next })
  const cells = previewCells(edit)
  const currentCells = gridCellCount(project.building.bounds_m.min_m, project.building.bounds_m.max_m, project.routing_config.grid_resolution_m)

  function apply(event: FormEvent) {
    event.preventDefault()
    try { onCommit(updateDomain(project, edit)) }
    catch (error) {
      onError(error instanceof Error ? error.message : '탐색 도메인을 변경하지 못했습니다.')
      setEdit(domainDraft(project))
    }
  }

  return (
    <details className="setup-card" open={open} onToggle={(event) => onToggle(event.currentTarget.open)}>
      <summary>
        <span className="setup-title">탐색 도메인</span>
        <span className="setup-summary">{formatSize(project)} m · 격자 {project.routing_config.grid_resolution_m} m · {currentCells.toLocaleString('ko-KR')}칸</span>
      </summary>
      <form onSubmit={apply} className="setup-form">
        <p className="setup-help">도면(캔버스)이 곧 경로 탐색 범위입니다. 값은 세계좌표 m이며, 줄일 때 범위 밖에 남는 객체가 있으면 거부합니다.</p>
        <div className="setup-grid three">
          {axes.map((axis, index) => <label key={`min-${axis}`}>{axis} 최소 (m)<input type="number" step="any" value={edit.minText[index]} onChange={(event) => {
            const minText = [...edit.minText] as DomainEdit['minText']; minText[index] = event.target.value; setEdit({ ...edit, minText })
          }} /></label>)}
          {axes.map((axis, index) => <label key={`max-${axis}`}>{axis} 최대 (m)<input type="number" step="any" value={edit.maxText[index]} onChange={(event) => {
            const maxText = [...edit.maxText] as DomainEdit['maxText']; maxText[index] = event.target.value; setEdit({ ...edit, maxText })
          }} /></label>)}
        </div>
        <div className="setup-grid">
          {edit.floors.map((floor, index) => <div key={floor.id} className="setup-grid two">
            <label>{floor.id} 바닥 z (m)<input type="number" step="any" value={floor.zMinText} onChange={(event) => {
              setEdit({ ...edit, floors: edit.floors.map((item, i) => i === index ? { ...item, zMinText: event.target.value } : item) })
            }} /></label>
            <label>{floor.id} 천장 z (m)<input type="number" step="any" value={floor.zMaxText} onChange={(event) => {
              setEdit({ ...edit, floors: edit.floors.map((item, i) => i === index ? { ...item, zMaxText: event.target.value } : item) })
            }} /></label>
          </div>)}
        </div>
        <label className="setup-wide">격자 간격 (m) · 스냅 간격과 같음
          <input type="number" step="any" min="0.05" value={edit.gridText} onChange={(event) => setEdit({ ...edit, gridText: event.target.value })} />
        </label>
        <p className={cells !== null && cells > CELL_LIMIT ? 'setup-note bad' : cells !== null && cells > CELL_WARNING ? 'setup-note warn' : 'setup-note'}>
          {cells === null ? '격자 칸 수: 입력값을 확인해 주세요.' : `격자 칸 ${cells.toLocaleString('ko-KR')}개`}
          {cells !== null && cells > CELL_LIMIT && ` · 한도 ${CELL_LIMIT.toLocaleString('ko-KR')}개 초과, 적용할 수 없습니다.`}
          {cells !== null && cells > CELL_WARNING && cells <= CELL_LIMIT && ' · 경로 계산이 수십 초 이상 걸릴 수 있습니다.'}
          <br />격자가 굵으면 좁은 틈(약 격자 2칸 + 배관 외곽 지름 미만)이 막힐 수 있습니다.
        </p>
        <button type="submit" className="button-secondary" disabled={busy}>도메인 적용</button>
      </form>
    </details>
  )
}

function pipeDraft(pipe: Pipe | undefined) {
  return {
    outer: pipe ? String(metresToMillimetres(pipe.outer_diameter_m)) : '',
    insulation: pipe ? String(metresToMillimetres(pipe.insulation_thickness_m)) : '',
    margin: pipe ? String(metresToMillimetres(pipe.clearance_margin_m ?? 0)) : '',
  }
}

function PipeSection({ outer, insulation, margin }: { outer: number; insulation: number; margin: number }) {
  const total = outer / 2 + insulation + margin
  if (!(total > 0)) return null
  const scale = 54 / total
  return (
    <svg className="pipe-section" viewBox="0 0 120 120" role="img" aria-label="배관 단면: 외경, 보온재, 추가 마진">
      <circle cx="60" cy="60" r={total * scale} className="ring-margin" />
      <circle cx="60" cy="60" r={(outer / 2 + insulation) * scale} className="ring-insulation" />
      <circle cx="60" cy="60" r={(outer / 2) * scale} className="ring-pipe" />
    </svg>
  )
}

export function PipeSettings({ project, pipeId, onSelectPipe, busy, open, onToggle, onCommit, onError }: CommonProps & { pipeId: string; onSelectPipe: (id: string) => void }) {
  const pipe = project.pipes.find((item) => item.id === pipeId)
  const sourceKey = JSON.stringify(pipe ?? pipeId)
  const [state, setState] = useState(() => ({ sourceKey, draft: pipeDraft(pipe) }))
  if (state.sourceKey !== sourceKey) setState({ sourceKey, draft: pipeDraft(pipe) })
  const draft = state.sourceKey === sourceKey ? state.draft : pipeDraft(pipe)
  const setDraft = (next: ReturnType<typeof pipeDraft>) => setState({ sourceKey, draft: next })
  const numbers = [draft.outer, draft.insulation, draft.margin].map((text) => text.trim() ? Number(text) : Number.NaN)
  const previewOk = numbers.every(Number.isFinite) && numbers[0] > 0 && numbers[1] >= 0 && numbers[2] >= 0

  function apply(event: FormEvent) {
    event.preventDefault()
    if (!pipe) return
    try {
      onCommit(updatePipe(project, pipe.id, {
        outerDiameterText: millimetresToMetres(draft.outer),
        insulationText: millimetresToMetres(draft.insulation),
        marginText: millimetresToMetres(draft.margin),
      }))
    } catch (error) {
      onError(error instanceof Error ? error.message : '배관 단면을 변경하지 못했습니다.')
      setDraft(pipeDraft(pipe))
    }
  }

  return (
    <details className="setup-card" open={open} onToggle={(event) => onToggle(event.currentTarget.open)}>
      <summary>
        <span className="setup-title">배관 단면</span>
        <span className="setup-summary">{pipe
          ? `${pipe.id} · 외곽 지름 ${metresToMillimetres(pipeEnvelopeDiameter(pipe))} mm`
          : '배관 없음'}</span>
      </summary>
      {pipe ? <form onSubmit={apply} className="setup-form">
        <label className="setup-wide">배관<select value={pipe.id} disabled={busy} onChange={(event) => onSelectPipe(event.target.value)}>
          {project.pipes.map((item) => <option key={item.id} value={item.id}>{item.id} ({item.from_port_id} → {item.to_port_id})</option>)}
        </select></label>
        <div className="pipe-setup">
          <div className="setup-grid">
            <label><span><i className="swatch pipe" />외경 (mm)</span><input type="number" step="any" min="0" value={draft.outer} onChange={(event) => setDraft({ ...draft, outer: event.target.value })} /></label>
            <label><span><i className="swatch insulation" />보온재 두께 (mm)</span><input type="number" step="any" min="0" value={draft.insulation} onChange={(event) => setDraft({ ...draft, insulation: event.target.value })} /></label>
            <label><span><i className="swatch margin" />추가 마진 (mm)</span><input type="number" step="any" min="0" value={draft.margin} onChange={(event) => setDraft({ ...draft, margin: event.target.value })} /></label>
          </div>
          {previewOk && <PipeSection outer={numbers[0]} insulation={numbers[1]} margin={numbers[2]} />}
        </div>
        <p className="setup-note">
          {previewOk ? `외곽 지름 = 외경 + 2 × (보온재 + 마진) = ${Number((numbers[0] + 2 * (numbers[1] + numbers[2])).toFixed(3))} mm` : '값을 확인해 주세요.'}
          <br />장애물·Zone·건물 경계와의 간섭과 MIN_CLEARANCE 거리는 이 외곽에서 잽니다. 마진은 연구용 가정값이며 규정 값이 아닙니다.
        </p>
        <button type="submit" className="button-secondary" disabled={busy}>단면 적용</button>
      </form> : <p className="setup-help">프로젝트에 배관이 없습니다.</p>}
    </details>
  )
}
