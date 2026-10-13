import { Popup } from './Popup'

export function UnsavedChangesDialog({ action, busy, error, onSave, onDiscard, onCancel }: {
  action: string; busy: boolean; error: string; onSave: () => void; onDiscard: () => void; onCancel: () => void
}) {
  return <Popup title="저장되지 않은 변경" closeDisabled={busy} onClose={onCancel}>
    <p>{action} 전에 현재 프로젝트를 저장하시겠습니까?</p>
    <p>저장하지 않고 계속하면 현재 화면의 변경 내용이 서버에 보존되지 않습니다.</p>
    {error && <p className="library-error" role="alert">{error}</p>}
    <div className="button-row">
      <button type="button" className="button-primary" disabled={busy} onClick={onSave}>{busy ? '저장 중…' : '저장하고 계속'}</button>
      <button type="button" className="button-secondary" disabled={busy} onClick={onDiscard}>저장하지 않고 계속</button>
      <button type="button" className="button-secondary" disabled={busy} onClick={onCancel} data-initial-focus autoFocus>취소</button>
    </div>
  </Popup>
}
