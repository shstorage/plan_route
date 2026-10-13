import type { ProjectSummary } from '../api/client'
import { Popup } from './Popup'

export function DeleteProjectDialog({ project, current, busy, error, onDelete, onCancel }: {
  project: ProjectSummary; current: boolean; busy: boolean; error: string
  onDelete: () => void; onCancel: () => void
}) {
  return <Popup title="저장 프로젝트 삭제" closeDisabled={busy} onClose={onCancel}>
    <p><strong>{project.project_name || project.project_id}</strong>의 저장 파일을 삭제하시겠습니까?</p>
    <p className="delete-project-file">{project.project_id}.json · 저장 개정 {project.revision}</p>
    <p>삭제한 저장 파일은 되돌릴 수 없습니다. 기존 계산 결과 기록은 유지됩니다.</p>
    {current && <p>현재 화면의 편집 내용은 유지됩니다. 삭제 후에는 미저장 상태가 되며, 다시 저장하면 파일이 새로 만들어집니다.</p>}
    {error && <p className="library-error" role="alert">삭제되지 않음: {error}</p>}
    <div className="button-row">
      <button type="button" className="button-secondary" disabled={busy} onClick={onCancel} data-initial-focus autoFocus>취소</button>
      <button type="button" className="button-danger" disabled={busy} onClick={onDelete}>{busy ? '삭제 중…' : '저장 파일 삭제'}</button>
    </div>
  </Popup>
}
