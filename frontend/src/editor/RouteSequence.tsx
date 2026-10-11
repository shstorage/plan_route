import { Fragment } from 'react'
import type { EngineeringProject } from '../api/client'
import { reorderWaypoint, removeWaypoint, type Selection } from './model.ts'

type Props = {
  project: EngineeringProject
  pipeId: string
  selection: Selection | null
  busy: boolean
  adding: boolean
  onSelect: (selection: Selection) => void
  onAdd: () => void
  onCommit: (project: EngineeringProject) => void
  onError: (message: string) => void
}

/** The selected pipe's ordered route: start port → waypoint 1 … n → end port. */
export function RouteSequence({ project, pipeId, selection, busy, adding, onSelect, onAdd, onCommit, onError }: Props) {
  const pipe = project.pipes.find((item) => item.id === pipeId)
  if (!pipe) return null
  const waypoints = pipe.waypoints ?? []

  function change(task: () => EngineeringProject) {
    try { onCommit(task()) }
    catch (error) { onError(error instanceof Error ? error.message : '경유점 순서를 바꾸지 못했습니다.') }
  }

  const isSelected = (kind: Selection['kind'], id: string) => selection?.kind === kind && selection.id === id

  return (
    <div className="route-sequence" aria-label={`${pipe.id} 경로 순서`}>
      <span className="sequence-title">{pipe.id} 경로 순서</span>
      <ol className="sequence-chain">
        <li><button type="button" className={`sequence-chip start${isSelected('port', pipe.from_port_id) ? ' selected' : ''}`} onClick={() => onSelect({ kind: 'port', id: pipe.from_port_id })}><b>S</b>{pipe.from_port_id}</button></li>
        {waypoints.map((item, index) => (
          <Fragment key={item.id}>
            <li className="sequence-arrow" aria-hidden="true">→</li>
            <li className="sequence-step">
              <button type="button" className={`sequence-chip waypoint${isSelected('waypoint', item.id) ? ' selected' : ''}`} title={item.note ?? undefined} onClick={() => onSelect({ kind: 'waypoint', id: item.id })}>
                <b>{index + 1}</b>{item.id}{item.pass_axis && <small>{item.pass_axis.toUpperCase()}축 통과</small>}
              </button>
              {isSelected('waypoint', item.id) && <span className="sequence-tools">
                <button type="button" aria-label="앞으로" disabled={busy || index === 0} onClick={() => change(() => reorderWaypoint(project, item.id, -1))}>◀</button>
                <button type="button" aria-label="뒤로" disabled={busy || index === waypoints.length - 1} onClick={() => change(() => reorderWaypoint(project, item.id, 1))}>▶</button>
                <button type="button" aria-label="경유점 삭제" disabled={busy} onClick={() => change(() => removeWaypoint(project, item.id))}>✕</button>
              </span>}
            </li>
          </Fragment>
        ))}
        <li className="sequence-arrow" aria-hidden="true">→</li>
        <li><button type="button" className={`sequence-chip end${isSelected('port', pipe.to_port_id) ? ' selected' : ''}`} onClick={() => onSelect({ kind: 'port', id: pipe.to_port_id })}><b>E</b>{pipe.to_port_id}</button></li>
      </ol>
      <button type="button" className={adding ? 'tool active' : 'tool'} disabled={busy} onClick={onAdd}>+ 경유점 추가</button>
      {!waypoints.length && <span className="sequence-hint">벽 관통부처럼 꼭 지나야 하는 지점이 있으면 경유점을 추가하세요. 추가한 순서대로 지나갑니다.</span>}
    </div>
  )
}
