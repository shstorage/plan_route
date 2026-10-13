import { useEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { HostWindowContext } from './HostWindow'
import type { CompanionView, DetachedTarget } from './detachedWindow'

/** React still owns one project; the new window is another view of that state. */
export function DetachedView({ view, target, name, children, locked, onClose, onReturn }: {
  view: CompanionView; target: DetachedTarget; name: string; children: ReactNode; locked: boolean
  onClose: (view: CompanionView, target: DetachedTarget) => void
  onReturn: (view: CompanionView, target: DetachedTarget) => void
}) {
  const lifecycle = useRef(0)
  useEffect(() => {
    const counter = lifecycle
    const generation = ++counter.current
    const child = target.window
    const copyStyles = () => {
      if (child.closed) return
      child.document.head.querySelectorAll('[data-companion-style]').forEach((node) => node.remove())
      document.head.querySelectorAll('style, link[rel="stylesheet"]').forEach((node) => {
        const copy = node.cloneNode(true) as HTMLElement
        copy.dataset.companionStyle = 'true'
        if (node instanceof HTMLLinkElement) (copy as HTMLLinkElement).href = node.href
        child.document.head.append(copy)
      })
    }
    copyStyles()
    // Covers lazy 3D CSS and development HMR as well as production links.
    const styles = new MutationObserver(copyStyles)
    styles.observe(document.head, { childList: true, subtree: true, characterData: true, attributes: true })
    const closed = () => onClose(view, target)
    const closeWithParent = () => child.close()
    child.addEventListener('pagehide', closed)
    window.addEventListener('pagehide', closeWithParent)
    const timer = window.setInterval(() => { if (child.closed) closed() }, 1000)
    return () => {
      styles.disconnect()
      window.clearInterval(timer)
      child.removeEventListener('pagehide', closed)
      window.removeEventListener('pagehide', closeWithParent)
      // StrictMode replays setup/cleanup; close only after a real unmount.
      window.setTimeout(() => { if (counter.current === generation && !child.closed) child.close() }, 0)
    }
  }, [view, target, onClose])
  useEffect(() => {
    if (target.window.closed) return
    const doc = target.window.document
    const title = doc.querySelector('title') ?? doc.head.appendChild(doc.createElement('title'))
    title.replaceChildren(doc.createTextNode(`${view.toUpperCase()} · ${name} · plan_route`))
  }, [view, name, target])
  return createPortal(<HostWindowContext.Provider value={target.window}>
    <header className="detached-heading"><strong>{view.toUpperCase()} 보조 보기 · {name}</strong>
      <div className="popup-window-actions">
        <button type="button" className="button-secondary" title="이 창을 닫고 메인 창의 같은 보기에서 계속 작업합니다." onClick={() => onReturn(view, target)}>메인에서 계속</button>
        <button type="button" className="button-secondary" onClick={() => onClose(view, target)}>보조 창 닫기</button>
      </div>
    </header>
    {locked && <p className="detached-lock" role="status">메인 창에서 진행 중인 확인을 완료해 주세요.</p>}
    <main className="detached-body auxiliary-view" inert={locked}>{children}</main>
  </HostWindowContext.Provider>, target.container)
}
