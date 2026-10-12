import { useEffect, useState } from 'react'
import { listProjects, type ProjectList } from '../api/client'

export function ProjectLibrary({ active, refreshToken, currentId, busy, onLoad }: {
  active: boolean; refreshToken: number; currentId: string; busy: boolean; onLoad: (id: string) => void
}) {
  const [list, setList] = useState<ProjectList>({ projects: [], issues: [] })
  const [loading, setLoading] = useState(active)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [query, setQuery] = useState('')
  const requestKey = `${active}:${refreshToken}:${attempt}`
  const [followedRequest, setFollowedRequest] = useState(requestKey)
  // Mark a changed request pending before its network effect starts.
  if (followedRequest !== requestKey) {
    setFollowedRequest(requestKey)
    if (active) { setLoading(true); setError('') }
  }
  useEffect(() => {
    if (!active) return
    const controller = new AbortController()
    let alive = true
    listProjects(controller.signal).then((next) => { if (alive) setList(next) })
      .catch((err: unknown) => { if (alive) setError(err instanceof Error ? err.message : '목록을 불러오지 못했습니다.') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false; controller.abort() }
  }, [active, refreshToken, attempt])
  const search = query.trim().toLocaleLowerCase()
  const visible = list.projects.filter((item) => `${item.project_name ?? ''} ${item.project_id}`.toLocaleLowerCase().includes(search))
  return <section className="project-library" aria-label="저장된 프로젝트" aria-busy={loading}>
    <div className="library-heading"><h3>저장된 프로젝트 <small>{list.projects.length}개</small></h3><button type="button" className="button-secondary" disabled={loading} onClick={() => setAttempt((value) => value + 1)}>목록 새로고침</button></div>
    <input aria-label="저장 프로젝트 검색" placeholder="프로젝트 이름으로 검색" value={query} onChange={(event) => setQuery(event.target.value)} />
    {loading && <p role="status">저장 목록을 확인하는 중…</p>}
    {error && <p className="library-error" role="alert">목록 불러오기 실패: {error} · 목록 새로고침으로 다시 확인하세요.</p>}
    {!loading && !error && !list.projects.length && <p>아직 저장된 프로젝트가 없습니다. 화면 상단의 프로젝트 저장을 눌러 주세요.</p>}
    {!loading && !error && !!list.projects.length && !visible.length && <p>검색 결과가 없습니다.</p>}
    <ul className="saved-project-list">{visible.map((item) => <li key={item.project_id} data-project-id={item.project_id}>
      <div><strong>{item.project_name || item.project_id}</strong>{item.project_id === currentId && <span className="soft-badge">현재 작업</span>}
        <small>기기 {item.equipment_count} · 배관 {item.pipe_count} · 개정 {item.revision} · {new Date(item.updated_at).toLocaleString('ko-KR')}</small>
      </div>
      <button type="button" className="button-secondary" disabled={busy || loading || !!error} onClick={() => onLoad(item.project_id)}>불러오기</button>
    </li>)}</ul>
    {!!list.issues.length && <p className="library-error" role="alert">검증하지 못한 저장 파일 {list.issues.length}개: {list.issues.map((issue) => issue.filename).join(', ')}. 해당 파일은 목록에서 제외했습니다.</p>}
  </section>
}
