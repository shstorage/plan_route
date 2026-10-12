import { useState } from 'react'
import { Popup } from './Popup'

export function ProjectActions({ name, busy, canSave, onSave, onNew, onRename, dirty }: {
  name: string; busy: boolean; canSave: boolean; onSave: (name: string) => void; onNew: () => void; onRename: (name: string) => void; dirty: boolean
}) {
  const [draft, setDraft] = useState(name)
  const [sourceName, setSourceName] = useState(name)
  if (sourceName !== name) { setSourceName(name); setDraft(name) }
  return <div className="project-filebar">
    <form onSubmit={(event) => { event.preventDefault(); onSave(draft) }}>
      <label>프로젝트 이름<input aria-label="프로젝트 이름" value={draft} maxLength={100} required disabled={busy || !canSave} onChange={(event) => setDraft(event.target.value)} onBlur={() => { if (draft !== name) onRename(draft) }} /></label>
      <button type="submit" className="button-primary" disabled={busy || !canSave}>{busy ? '작업 중…' : '프로젝트 저장'}</button>
      <span className={`project-save-state ${dirty || draft !== name ? 'dirty' : ''}`} role="status">{dirty || draft !== name ? '저장되지 않은 변경 있음' : '저장됨'}</span>
    </form>
    <button type="button" className="button-secondary" disabled={busy} onClick={onNew}>+ 새 프로젝트</button>
  </div>
}

export function NewProjectDialog({ onCreate, onClose }: { onCreate: (name: string) => void; onClose: () => void }) {
  const [name, setName] = useState('새 프로젝트')
  const [error, setError] = useState('')
  return <Popup title="새 프로젝트 만들기" onClose={onClose}><form className="new-project-form" onSubmit={(event) => { event.preventDefault(); if (!name.trim()) { setError('프로젝트 이름을 입력해 주세요.'); return } onCreate(name) }}>
    <label>프로젝트 이름<input aria-label="새 프로젝트 이름" value={name} onChange={(event) => setName(event.target.value)} required maxLength={100} autoFocus /></label>
    <p>빈 건물에서 시작합니다. 배치·연결을 편집하면 JSON이 자동으로 만들어져 저장 전에도 계산할 수 있습니다.</p>
    {error && <p role="alert">{error}</p>}
    <div className="button-row"><button type="submit" className="button-primary">프로젝트 만들기</button><button type="button" className="button-secondary" onClick={onClose}>취소</button></div>
  </form></Popup>
}
