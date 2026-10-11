import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import {
  API_BASE_URL,
  ApiError,
  exampleLabels,
  getExampleProject,
  getHealth,
  loadProject,
  saveProject,
  solveRoute,
  validateProject,
  type EngineeringProject,
  type ExampleProject,
  type RouteSolveReport,
  type ValidationIssue,
} from './api/client'
import { PlanEditor } from './editor/PlanEditor'
import type { Selection } from './editor/model.ts'
import { pushHistory, redoHistory, undoHistory, type History } from './editor/history.ts'
import './App.css'

// three.js is loaded only when the 3D view is first rendered, keeping it out of the main bundle.
const Viewer3D = lazy(() => import('./viewer/Viewer3D'))

type ConnectionState =
  | { status: 'loading' }
  | { status: 'success' }
  | { status: 'error'; message: string }

type Notice = {
  kind: 'success' | 'error'
  title: string
  message: string
  details?: ValidationIssue[]
}

type Operation = 'demo' | 'validate' | 'solve' | 'save' | 'load' | null

type ProjectOverview = {
  id: string
  schemaVersion: string
  pipeIds: string[]
  obstacles: number
  zones: number
  constraints: number
  resolution: number | null
}

const statusText: Record<RouteSolveReport['status'], string> = {
  SUCCESS: '경로 계산 완료',
  NO_PATH: '경로 없음',
  SEARCH_LIMIT_REACHED: '검색 한도 도달',
  INVALID_INPUT: '입력 오류',
  UNAPPROVED_RULE: '미승인 규칙',
  RULE_CONFLICT: '규칙과 포트 충돌',
  INVALID_ROUTE: '최종 기하 검증 실패',
  RULES_NOT_COMPILED: '규칙 컴파일 필요',
  WAYPOINT_BLOCKED: '경유점이 막힘',
}

const statusHelp: Record<RouteSolveReport['status'], string> = {
  SUCCESS: '격자 탐색과 독립 기하 검증을 통과했습니다.',
  NO_PATH: '현재 장애물과 승인 규칙 아래에서는 연결 경로가 없습니다.',
  SEARCH_LIMIT_REACHED: '탐색 횟수 한도에 도달했습니다. 경로가 없다는 뜻은 아닙니다.',
  INVALID_INPUT: '프로젝트나 배관 설정을 확인해 주세요.',
  UNAPPROVED_RULE: '대상 배관에 미승인 규칙이 있어 실행하지 않았습니다.',
  RULE_CONFLICT: '승인 규칙이 연결 포트를 막아 경로를 시작하거나 끝낼 수 없습니다.',
  INVALID_ROUTE: '탐색 경로가 원본 연속 형상 검증을 통과하지 못했습니다.',
  RULES_NOT_COMPILED: '승인 규칙을 먼저 컴파일해야 합니다.',
  WAYPOINT_BLOCKED: '경유점이 장애물·건물 경계·승인 규칙 영역 안에 있습니다. 경유점 위치를 옮겨 주세요.',
}

const violationText: Record<string, string> = {
  OBSTACLE_COLLISION: '장애물 충돌',
  BUILDING_BOUNDARY: '건물 경계',
  ENDPOINT_MISMATCH: '끝점 불일치',
  KEEP_OUT: '진입 금지',
  MIN_CLEARANCE: '최소 이격',
  WAYPOINT_MISSED: '경유점 누락',
  WAYPOINT_DIRECTION: '경유점 통과 방향',
  SELF_CLEARANCE: '자기 간섭(배관끼리 겹침)',
}

/** Korean notes for solver messages that accompany a usable result. */
function routeNote(message: string): string | null {
  if (message.includes('re-searched one at a time')) {
    return '경유점 구간끼리 겹쳐서, 앞 구간을 피하도록 구간별로 다시 탐색했습니다. 순서 전체의 최적 경로라는 보장은 없습니다.'
  }
  if (message.includes('leg-by-leg re-search failed')) {
    return '경유점 구간끼리 겹치며, 구간별 재탐색으로도 피하지 못했습니다. 경유점이나 포트 위치를 조정해 주세요.'
  }
  return null
}

function overviewFromText(text: string): ProjectOverview | null {
  try {
    const value: unknown = JSON.parse(text)
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return null
    const data = value as Record<string, unknown>
    const pipes = Array.isArray(data.pipes) ? data.pipes : []
    const ids = pipes.flatMap((pipe: unknown) => {
      if (typeof pipe !== 'object' || pipe === null || !('id' in pipe)) return []
      return typeof pipe.id === 'string' ? [pipe.id] : []
    })
    const routing = data.routing_config
    const resolution = typeof routing === 'object' && routing !== null && 'grid_resolution_m' in routing && typeof routing.grid_resolution_m === 'number'
      ? routing.grid_resolution_m
      : null
    return {
      id: typeof data.project_id === 'string' ? data.project_id : 'ID 없음',
      schemaVersion: typeof data.schema_version === 'string' ? data.schema_version : '—',
      pipeIds: ids,
      obstacles: Array.isArray(data.obstacles) ? data.obstacles.length : 0,
      zones: Array.isArray(data.zones) ? data.zones.length : 0,
      constraints: Array.isArray(data.constraints) ? data.constraints.length : 0,
      resolution,
    }
  } catch {
    return null
  }
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—'
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('ko-KR')
}

function App() {
  const [connection, setConnection] = useState<ConnectionState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [projectText, setProjectText] = useState('')
  const [editorProject, setEditorProject] = useState<EngineeringProject | null>(null)
  const [past, setPast] = useState<string[]>([])
  const [future, setFuture] = useState<string[]>([])
  const [projectLabel, setProjectLabel] = useState('예제 불러오는 중')
  const [example, setExample] = useState<ExampleProject>('starter')
  const [selectedPipeId, setSelectedPipeId] = useState('')
  const [selection, setSelection] = useState<Selection | null>(null)
  const [focusRuleId, setFocusRuleId] = useState('')
  const [lookupId, setLookupId] = useState('')
  const [savedMeta, setSavedMeta] = useState<{ revision: number; updatedAt: string } | null>(null)
  const [validatedId, setValidatedId] = useState<string | null>(null)
  const [route, setRoute] = useState<RouteSolveReport | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)
  const [operation, setOperation] = useState<Operation>(null)
  const overview = useMemo(() => overviewFromText(projectText), [projectText])

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    let timedOut = false
    const timeout = window.setTimeout(() => {
      timedOut = true
      controller.abort()
    }, 5000)

    getHealth(controller.signal)
      .then(() => { if (active) setConnection({ status: 'success' }) })
      .catch((error: unknown) => {
        if (!active) return
        setConnection({
          status: 'error',
          message: timedOut
            ? '서버가 5초 안에 응답하지 않았습니다.'
            : error instanceof Error ? error.message : '서버에 연결할 수 없습니다.',
        })
      })
      .finally(() => window.clearTimeout(timeout))

    return () => {
      active = false
      window.clearTimeout(timeout)
      controller.abort()
    }
  }, [attempt])

  useEffect(() => {
    const controller = new AbortController()
    getExampleProject('starter', controller.signal)
      .then((project) => {
        setProjectText(JSON.stringify(project, null, 2))
        setEditorProject(project)
        setProjectLabel(exampleLabels.starter)
        setSelectedPipeId(project.pipes[0]?.id ?? '')
        setLookupId(project.project_id)
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setProjectLabel('예제를 불러오지 못했습니다')
        setNotice({
          kind: 'error',
          title: '예제 불러오기 실패',
          message: error instanceof Error ? error.message : '서버에 연결할 수 없습니다.',
        })
      })
    return () => controller.abort()
  }, [])

  function applyProject(project: EngineeringProject, label: string) {
    setProjectText(JSON.stringify(project, null, 2))
    setEditorProject(project)
    setPast([])
    setFuture([])
    setSelection(null)
    setProjectLabel(label)
    setSelectedPipeId(project.pipes[0]?.id ?? '')
    setLookupId(project.project_id)
    setValidatedId(null)
    setRoute(null)
  }

  function editedProject(): unknown {
    if (!projectText.trim()) throw new Error('프로젝트 JSON이 비어 있습니다.')
    try {
      return JSON.parse(projectText) as unknown
    } catch {
      throw new Error('JSON 문법이 올바르지 않습니다. 쉼표와 따옴표를 확인해 주세요.')
    }
  }

  function applyHistory(history: History) {
    setPast(history.past)
    setFuture(history.future)
    setProjectText(history.present)
    setEditorProject(JSON.parse(history.present) as EngineeringProject)
    setValidatedId(null)
    setRoute(null)
    setSavedMeta(null)
  }

  function commitEditorProject(project: EngineeringProject) {
    const current: History = { past, present: projectText, future }
    const next = pushHistory(current, JSON.stringify(project, null, 2))
    if (next === current) return
    applyHistory(next)
    setProjectLabel('도면 편집 중')
    setNotice(null)
  }

  function undoEditor() {
    if (past.length) applyHistory(undoHistory({ past, present: projectText, future }))
  }

  function redoEditor() {
    if (future.length) applyHistory(redoHistory({ past, present: projectText, future }))
  }

  async function run(name: Exclude<Operation, null>, task: () => Promise<void>) {
    if (operation) return
    setOperation(name)
    setNotice(null)
    try {
      await task()
    } catch (error) {
      setNotice({
        kind: 'error',
        title: '작업 실패',
        message: error instanceof Error ? error.message : '요청을 처리하지 못했습니다.',
        details: error instanceof ApiError ? error.details : undefined,
      })
    } finally {
      setOperation(null)
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark">⌁</span><span>plan_route</span></div>
        <div className={`connection-pill ${connection.status}`} role="status" aria-live="polite">
          <span className="connection-dot" />
          {connection.status === 'loading' && '서버 확인 중'}
          {connection.status === 'success' && '백엔드 연결됨'}
          {connection.status === 'error' && '백엔드 연결 실패'}
        </div>
      </header>

      <main className="content">
        <section className="intro">
          <div>
            <p className="eyebrow">SYNTHETIC ROUTE STUDY · P08</p>
            <h1>도면에서 배치하고<br /><span>경로를 확인하세요.</span></h1>
            <p className="lead">층별 2D 도면에서 합성 건물의 벽체·Zone·Port를 편집하고, 승인 규칙을 적용한 경로를 계산합니다.</p>
          </div>
          <div className="intro-aside">
            <div className="aside-icon">3D</div>
            <strong>세계좌표 기반 2D 편집기</strong>
            <span>도면 조작은 EngineeringProject JSON의 m 좌표로 저장되고, 3D 보기는 같은 JSON에서 다시 그려집니다.</span>
          </div>
        </section>

        {connection.status === 'error' && (
          <div className="banner error" role="alert">
            <strong>백엔드 연결 실패</strong>
            <span>{connection.message} · {API_BASE_URL}을 확인해 주세요.</span>
            <button type="button" className="button-ghost" onClick={() => {
              setConnection({ status: 'loading' })
              setAttempt((value) => value + 1)
            }}>다시 확인</button>
          </div>
        )}

        {editorProject ? (
          <PlanEditor
            key={editorProject.project_id}
            project={editorProject}
            route={route?.pipe_id === selectedPipeId ? route : null}
            selectedPipeId={selectedPipeId}
            selection={selection}
            onSelectionChange={setSelection}
            focusRuleId={focusRuleId}
            onFocusRule={setFocusRuleId}
            busy={operation !== null}
            canUndo={past.length > 0}
            canRedo={future.length > 0}
            onUndo={undoEditor}
            onRedo={redoEditor}
            onCommit={commitEditorProject}
            onSelectPipe={(pipeId) => { setSelectedPipeId(pipeId); setRoute(null) }}
          />
        ) : <section className="panel editor-placeholder"><p className="step">02 / PLAN EDITOR</p><h2>도면 준비 중</h2><p>예제를 불러오거나 수정한 JSON을 검증하면 층별 배치도가 나타납니다.</p></section>}

        {editorProject && (
          <Suspense fallback={<section className="panel viewer3d"><div className="viewer-loading">3D 보기 불러오는 중…</div></section>}>
            <Viewer3D
              project={editorProject}
              route={route?.pipe_id === selectedPipeId ? route : null}
              selectedPipeId={selectedPipeId}
              selection={selection}
              onSelect={setSelection}
              focusRuleId={focusRuleId}
              onFocusRule={setFocusRuleId}
            />
          </Suspense>
        )}

        <section className="workspace" aria-label="프로젝트 작업대">
          <div className="left-column">
            <section className="panel project-panel">
              <div className="panel-heading">
                <div><p className="step">01 / PROJECT</p><h2>프로젝트</h2></div>
                <span className="soft-badge">{projectLabel}</span>
              </div>
              <p className="panel-description">서버의 합성 예제를 불러오거나 JSON을 수정한 뒤 검증하고 저장할 수 있습니다.</p>
              <div className="button-row">
                <select aria-label="합성 예제" value={example} disabled={operation !== null} onChange={(event) => setExample(event.target.value as ExampleProject)}>
                  {(Object.keys(exampleLabels) as ExampleProject[]).map((name) => <option key={name} value={name}>{exampleLabels[name]}</option>)}
                </select>
                <button type="button" className="button-secondary" disabled={operation !== null} onClick={() => run('demo', async () => {
                  const project = await getExampleProject(example)
                  applyProject(project, exampleLabels[example])
                  setSavedMeta(null)
                  setNotice({ kind: 'success', title: '예제 준비 완료', message: `${project.project_id} 프로젝트를 불러왔습니다.` })
                })}>예제 불러오기</button>
                <button type="button" className="button-secondary" disabled={operation !== null || !projectText} onClick={() => run('save', async () => {
                  const saved = await saveProject(editedProject())
                  setSavedMeta({ revision: saved.revision, updatedAt: saved.updated_at })
                  setLookupId(saved.project_id)
                  setNotice({ kind: 'success', title: '서버에 저장됨', message: `${saved.project_id} · 개정 ${saved.revision} · ${formatDate(saved.updated_at)}` })
                })}>서버에 저장</button>
              </div>
              <div className="load-row">
                <label htmlFor="project-id">저장된 프로젝트 ID</label>
                <div>
                  <input id="project-id" value={lookupId} disabled={operation !== null} onChange={(event) => setLookupId(event.target.value)} placeholder="예: SYNTH-DEMO-001" />
                  <button type="button" className="button-secondary" disabled={operation !== null} onClick={() => run('load', async () => {
                    if (!lookupId.trim()) throw new Error('불러올 프로젝트 ID를 입력해 주세요.')
                    const loaded = await loadProject(lookupId.trim())
                    applyProject(loaded.project, '서버에서 불러옴')
                    setSavedMeta({ revision: loaded.revision, updatedAt: loaded.updatedAt })
                    setNotice({ kind: 'success', title: '프로젝트 불러오기 완료', message: `${loaded.project.project_id} · 개정 ${loaded.revision}` })
                  })}>불러오기</button>
                </div>
              </div>
              <div className="overview-grid" aria-label="프로젝트 요약">
                <div><span>프로젝트 ID</span><strong>{overview?.id ?? '—'}</strong></div>
                <div><span>스키마</span><strong>{overview?.schemaVersion ?? '—'}</strong></div>
                <div><span>장애물 / Zone</span><strong>{overview ? `${overview.obstacles} / ${overview.zones}` : '—'}</strong></div>
                <div><span>배관 / 규칙</span><strong>{overview ? `${overview.pipeIds.length} / ${overview.constraints}` : '—'}</strong></div>
              </div>
              {savedMeta && <p className="saved-meta">저장 개정 {savedMeta.revision} · {formatDate(savedMeta.updatedAt)}</p>}
              <label htmlFor="project-json" className="field-label">EngineeringProject JSON <span>세계좌표 단위 m · z 수직</span></label>
              <textarea
                id="project-json"
                spellCheck={false}
                disabled={operation !== null}
                value={projectText}
                onChange={(event) => {
                  const nextText = event.target.value
                  const nextPipeIds = overviewFromText(nextText)?.pipeIds ?? []
                  setProjectText(nextText)
                  setEditorProject(null)
                  setPast([])
                  setFuture([])
                  if (!nextPipeIds.includes(selectedPipeId)) {
                    setSelectedPipeId(nextPipeIds[0] ?? '')
                  }
                  setProjectLabel('편집 중')
                  setValidatedId(null)
                  setRoute(null)
                  setSavedMeta(null)
                  setNotice(null)
                }}
                placeholder="백엔드를 실행하면 합성 예제 JSON이 자동으로 나타납니다."
              />
              <div className="validation-row">
                <button type="button" className="button-secondary" disabled={operation !== null || !projectText} onClick={() => run('validate', async () => {
                  const result = await validateProject(editedProject())
                  setValidatedId(result.project_id)
                  setEditorProject(editedProject() as EngineeringProject)
                  setNotice({ kind: 'success', title: '스키마 검증 통과', message: `${result.project_id} · 버전 ${result.schema_version}` })
                })}>JSON 검증</button>
                <span>{validatedId ? `검증 완료 · ${validatedId}` : '변경한 JSON은 검증 후 실행하세요.'}</span>
              </div>
            </section>
          </div>

          <div className="right-column">
            <section className="panel run-panel">
              <div className="panel-heading"><div><p className="step">04 / ROUTE</p><h2>경로 탐색</h2></div><span className="soft-badge">3D A* + 독립 검증</span></div>
              <p className="panel-description">선택한 배관에 승인된 규칙을 적용하고 경로를 계산합니다.</p>
              <div className="run-controls">
                <label htmlFor="pipe-id">배관 ID</label>
                <select id="pipe-id" value={selectedPipeId} onChange={(event) => { setSelectedPipeId(event.target.value); setRoute(null) }} disabled={operation !== null}>
                  {overview?.pipeIds.length ? overview.pipeIds.map((id) => <option key={id} value={id}>{id}</option>) : <option value="">배관 없음</option>}
                </select>
                <button type="button" className="button-primary" disabled={operation !== null || !projectText || !selectedPipeId} onClick={() => run('solve', async () => {
                  const result = await solveRoute(editedProject(), selectedPipeId)
                  setRoute(result)
                })}>{operation === 'solve' ? '계산 중…' : '경로 계산 실행'} <span aria-hidden="true">↗</span></button>
              </div>
              <p className="run-hint">격자 간격 {overview?.resolution ?? '—'} m · 승인되지 않은 규칙은 실행되지 않습니다.</p>
            </section>

            {notice && (
              <div className={`banner ${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}>
                <strong>{notice.title}</strong><span>{notice.message}</span>
                {!!notice.details?.length && <ul className="issue-list">{notice.details.map((item, index) => <li key={`${item.location.join('.')}-${index}`}><code>{item.location.join(' → ')}</code> {item.message}</li>)}</ul>}
              </div>
            )}

            <section className="panel result-panel" aria-live="polite">
              <div className="panel-heading"><div><p className="step">05 / RESULT</p><h2>계산 결과</h2></div>{route && <span className={`result-chip ${route.status === 'SUCCESS' ? 'good' : 'bad'}`}>{route.status}</span>}</div>
              {!route ? (
                <div className="empty-result">
                  <div className="empty-symbol">⌁</div>
                  <strong>아직 계산 결과가 없습니다.</strong>
                  <p>예제 프로젝트를 확인한 뒤 ‘경로 계산 실행’을 눌러 주세요. 경로와 검증 결과가 여기에 표시됩니다.</p>
                </div>
              ) : (
                <>
                  <div className={`result-message ${route.status === 'SUCCESS' ? 'good' : 'bad'}`}>
                    <strong>{statusText[route.status]}</strong>
                    <span>{statusHelp[route.status]}</span>
                    {route.message && routeNote(route.message) && <small className="route-note">{routeNote(route.message)}</small>}
                    {route.message && <small>상세: {route.message}</small>}
                  </div>
                  <div className="metric-grid">
                    <div><span>경로 길이</span><strong>{formatNumber(route.cost_breakdown?.path_length_m)} <em>m</em></strong></div>
                    <div><span>방향 전환</span><strong>{route.bend_count ?? '—'} <em>회</em></strong></div>
                    <div><span>목적 비용</span><strong>{formatNumber(route.cost_breakdown?.total_objective_cost)}</strong></div>
                    <div><span>검증 위반</span><strong>{route.validation ? route.validation.violations.length : '—'} <em>건</em></strong></div>
                  </div>
                  <div className="result-details">
                    <div><span>탐색한 상태</span><strong>{route.expanded_states.toLocaleString('ko-KR')}</strong></div>
                    <div><span>실행 시간</span><strong>{formatNumber(route.runtime_ms, 1)} ms</strong></div>
                    <div><span>적용 규칙</span><strong>{route.applied_rule_ids.join(', ') || '없음'}</strong></div>
                    <div><span>독립 검증</span><strong>{route.validation?.status ?? '미실행'}</strong></div>
                  </div>
                  {!!route.validation?.violations.length && (
                    <div className="table-block">
                      <h3>위반 내역</h3>
                      <div className="table-scroll"><table><thead><tr><th>구간</th><th>위반</th><th>대상 / 규칙</th><th>측정 / 요구 (m)</th></tr></thead><tbody>
                        {route.validation.violations.map((violation, index) => <tr key={`${violation.segment_index}-${violation.object_id}-${index}`}><td>{violation.segment_index}</td><td>{violationText[violation.code] ?? violation.code}<small>{violation.code}</small></td><td>{violation.object_id}{violation.rule_id && <small>{violation.rule_id}</small>}</td><td>{formatNumber(violation.measured_distance_m, 3)} / {formatNumber(violation.required_distance_m, 3)}</td></tr>)}
                      </tbody></table></div>
                    </div>
                  )}
                  {!!route.points_m.length && (
                    <div className="table-block">
                      <div className="table-heading"><h3>경로 좌표</h3><span>{route.points_m.length}개 점 · 세계좌표 m</span></div>
                      <div className="table-scroll coordinates"><table><thead><tr><th>#</th><th>X (m)</th><th>Y (m)</th><th>Z (m)</th></tr></thead><tbody>
                        {route.points_m.map((point, index) => <tr key={index}><td>{index + 1}</td><td>{formatNumber(point[0], 3)}</td><td>{formatNumber(point[1], 3)}</td><td>{formatNumber(point[2], 3)}</td></tr>)}
                      </tbody></table></div>
                    </div>
                  )}
                  <details className="provenance"><summary>재현 정보</summary><dl><dt>시나리오 해시</dt><dd>{route.scenario_hash}</dd><dt>결과 ID</dt><dd>{route.result_id ?? '—'}</dd><dt>알고리즘</dt><dd>{route.algorithm}</dd></dl></details>
                </>
              )}
            </section>
          </div>
        </section>
      </main>

      <footer className="footer"><span>plan_route · 합성 3D 건물 연구 도구</span><span>실제 원전 배관 설계 또는 인허가 적합성 판단에 사용하지 않습니다.</span></footer>
    </div>
  )
}

export default App
