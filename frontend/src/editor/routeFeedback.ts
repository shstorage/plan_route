import type { EngineeringProject, RouteSolveReport } from '../api/client'
import { selectionLabel } from './model.ts'

type FailureReport = Pick<RouteSolveReport, 'status' | 'message'>

/** Decode the compiler's explicit endpoint failure; never infer a missing port ID. */
export function failedPortId(project: EngineeringProject, report: FailureReport | null): string | null {
  if (report?.status !== 'INVALID_INPUT') return null
  const match = report.message?.match(/port ([A-Za-z][A-Za-z0-9_-]*)(?: snaps to a physical blocked cell|: point_m is outside grid bounds)/)
  return match && project.equipment.some((item) => item.ports.some((port) => port.id === match[1])) ? match[1] : null
}

export function routeFailureText(project: EngineeringProject, report: FailureReport): string {
  const id = failedPortId(project, report)
  if (id) {
    const port = project.equipment.flatMap((item) => item.ports).find((item) => item.id === id)!
    const label = selectionLabel(project, { kind: 'port', id })
    const position = port.position_m.map((value) => value.toFixed(2)).join(', ')
    if (report.message?.includes('outside grid bounds')) return `${label} (${position} m)이 탐색 격자 밖에 있습니다. 연결점을 건물 경계 안쪽으로 옮겨 주세요.`
    return `${label} (${position} m)이 속한 격자가 기기·벽 또는 건물 경계로 막혀 있습니다. 배관 외경·보온재·격자 간격도 영향을 줍니다. 연결점이나 주변 기기 위치를 조정한 뒤 다시 계산하세요. 저장 여부와는 관계없습니다.`
  }
  if (report.status === 'INVALID_INPUT' && report.message?.includes('port-to-cell snap distance')) return '연결점에서 격자 중심까지의 거리가 허용값을 넘었습니다. 연결점 위치와 격자 간격을 확인하세요.'
  if (report.status === 'NO_PATH') return '현재 장애물과 승인 규칙 아래에서 경로를 찾지 못했습니다. 기기·벽·구역 배치와 연결점 방향을 확인하세요.'
  if (report.status === 'SEARCH_LIMIT_REACHED') return '검색 한도에 도달했습니다. 경로가 없다는 뜻은 아닙니다. 계산 결과 탭에서 상세 내용을 확인하세요.'
  if (report.status === 'INVALID_INPUT') return `입력 설정을 확인해 주세요. ${report.message || '계산 결과 탭에 상세 정보가 있습니다.'}`
  return `계산 결과: ${report.status}. ${report.message || '계산 결과 탭에서 상세 내용을 확인하세요.'}`
}
