import type { EngineeringProject, RouteSolveReport } from '../api/client'
import type { Selection } from './model'
import { failedPortId, routeFailureText } from './routeFeedback'

export function RouteStatusNotice({ project, route, busy, onSelect }: {
  project: EngineeringProject; route: RouteSolveReport | null; busy: boolean; onSelect: (selection: Selection) => void
}) {
  if (!route) return null
  const portId = failedPortId(project, route)
  return <div className={`plan-result-strip ${route.status === 'SUCCESS' ? 'good' : 'bad'}`} role={route.status === 'SUCCESS' ? 'status' : 'alert'}>
    {route.status !== 'SUCCESS' && <strong>계산 결과: {route.status}</strong>}
    <span>{route.status === 'SUCCESS' ? `계산 완료 · 길이 ${route.cost_breakdown?.path_length_m.toFixed(2) ?? '—'} m · 방향 전환 ${route.bend_count}회 · 검증 위반 ${route.validation?.violations.length ?? '—'}건` : routeFailureText(project, route)}</span>
    {portId && <button className="button-secondary" type="button" disabled={busy} onClick={() => onSelect({ kind: 'port', id: portId })}>막힌 연결점 선택</button>}
  </div>
}
